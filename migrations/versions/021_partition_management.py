"""Add partition management functions for flow_records.

Creates functions to:
1. Automatically create daily partitions
2. Drop old partitions based on retention policy
3. Migrate data from DEFAULT partition to proper date partitions

Revision ID: 021
Revises: 020
Create Date: 2025-12-29 21:45:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # 1. Function to create a partition for a specific date
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION create_flow_partition(
            p_date DATE
        ) RETURNS TEXT AS $$
        DECLARE
            partition_name TEXT;
            start_date DATE;
            end_date DATE;
        BEGIN
            partition_name := 'flow_records_' || to_char(p_date, 'YYYY_MM_DD');
            start_date := p_date;
            end_date := p_date + INTERVAL '1 day';

            -- Check if partition already exists
            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = partition_name AND n.nspname = 'public'
            ) THEN
                RETURN 'Partition ' || partition_name || ' already exists';
            END IF;

            -- Create the partition
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF flow_records
                 FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                start_date,
                end_date
            );

            RETURN 'Created partition ' || partition_name;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # 2. Function to create partitions for a date range (e.g., next 7 days)
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION create_flow_partitions_range(
            p_start_date DATE DEFAULT CURRENT_DATE,
            p_days_ahead INTEGER DEFAULT 7
        ) RETURNS TABLE (partition_name TEXT, status TEXT) AS $$
        DECLARE
            current_date DATE;
            result TEXT;
        BEGIN
            FOR i IN 0..p_days_ahead LOOP
                current_date := p_start_date + i;
                result := create_flow_partition(current_date);
                partition_name := 'flow_records_' || to_char(current_date, 'YYYY_MM_DD');
                status := result;
                RETURN NEXT;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # 3. Function to drop partitions older than retention period
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION drop_old_flow_partitions(
            p_retention_days INTEGER DEFAULT 7
        ) RETURNS TABLE (partition_name TEXT, status TEXT) AS $$
        DECLARE
            rec RECORD;
            partition_date DATE;
            cutoff_date DATE;
        BEGIN
            cutoff_date := CURRENT_DATE - p_retention_days;

            FOR rec IN
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_inherits i ON i.inhrelid = c.oid
                JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE n.nspname = 'public'
                  AND parent.relname = 'flow_records'
                  AND c.relname ~ '^flow_records_[0-9]{4}_[0-9]{2}_[0-9]{2}$'
            LOOP
                -- Extract date from partition name
                partition_date := to_date(
                    substring(rec.relname from 'flow_records_(.*)'),
                    'YYYY_MM_DD'
                );

                IF partition_date < cutoff_date THEN
                    EXECUTE format('DROP TABLE IF EXISTS %I', rec.relname);
                    partition_name := rec.relname;
                    status := 'Dropped (older than ' || cutoff_date || ')';
                    RETURN NEXT;
                END IF;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # 4. Function to migrate data from DEFAULT partition to proper partitions
    #    Run this during low-traffic periods as it moves data
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION migrate_default_partition_data(
            p_batch_size INTEGER DEFAULT 10000
        ) RETURNS TABLE (
            partition_date DATE,
            rows_migrated BIGINT,
            status TEXT
        ) AS $$
        DECLARE
            rec RECORD;
            migrated BIGINT;
            partition_name TEXT;
        BEGIN
            -- Get distinct dates in the default partition
            FOR rec IN
                SELECT DISTINCT date_trunc('day', timestamp)::date as flow_date,
                       count(*) as row_count
                FROM flow_records_default
                GROUP BY date_trunc('day', timestamp)::date
                ORDER BY flow_date
            LOOP
                -- Ensure partition exists for this date
                PERFORM create_flow_partition(rec.flow_date);
                partition_name := 'flow_records_' || to_char(rec.flow_date, 'YYYY_MM_DD');

                -- Move data in batches
                migrated := 0;
                LOOP
                    WITH moved AS (
                        DELETE FROM flow_records_default
                        WHERE ctid IN (
                            SELECT ctid FROM flow_records_default
                            WHERE timestamp >= rec.flow_date
                              AND timestamp < rec.flow_date + INTERVAL '1 day'
                            LIMIT p_batch_size
                            FOR UPDATE SKIP LOCKED
                        )
                        RETURNING *
                    )
                    INSERT INTO flow_records
                    SELECT * FROM moved;

                    GET DIAGNOSTICS migrated = migrated + ROW_COUNT;

                    -- Exit when no more rows to move
                    EXIT WHEN NOT FOUND OR ROW_COUNT = 0;

                    -- Yield control periodically
                    PERFORM pg_sleep(0.01);
                END LOOP;

                partition_date := rec.flow_date;
                rows_migrated := migrated;
                status := 'Migrated to ' || partition_name;
                RETURN NEXT;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # 5. Maintenance function to run daily (create future + drop old partitions)
    # ==========================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION maintain_flow_partitions(
            p_days_ahead INTEGER DEFAULT 3,
            p_retention_days INTEGER DEFAULT 7
        ) RETURNS TABLE (action TEXT, partition_name TEXT, status TEXT) AS $$
        BEGIN
            -- Create upcoming partitions
            FOR partition_name, status IN
                SELECT * FROM create_flow_partitions_range(CURRENT_DATE, p_days_ahead)
            LOOP
                action := 'CREATE';
                RETURN NEXT;
            END LOOP;

            -- Drop old partitions
            FOR partition_name, status IN
                SELECT * FROM drop_old_flow_partitions(p_retention_days)
            LOOP
                action := 'DROP';
                RETURN NEXT;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ==========================================================================
    # 6. Create initial partitions for the next 7 days
    # ==========================================================================
    op.execute("SELECT * FROM create_flow_partitions_range(CURRENT_DATE, 7)")


def downgrade() -> None:
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS maintain_flow_partitions(INTEGER, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS migrate_default_partition_data(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS drop_old_flow_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_flow_partitions_range(DATE, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_flow_partition(DATE)")

    # Note: We don't drop the created partitions as they contain data.
    # To fully revert, manually run:
    #   DROP TABLE IF EXISTS flow_records_YYYY_MM_DD;

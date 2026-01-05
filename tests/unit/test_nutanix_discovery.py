from flowlens.discovery.nutanix import NutanixSnapshot


def test_nutanix_snapshot_build_asset_metadata() -> None:
    snapshot = NutanixSnapshot(
        vms=[
            {
                "metadata": {
                    "uuid": "vm-1",
                    "name": "worker-01",
                    "categories": {"app": "payments"},
                },
                "spec": {"name": "worker-01"},
                "status": {
                    "cluster_reference": {"uuid": "cluster-1"},
                    "resources": {
                        "power_state": "ON",
                        "nic_list": [
                            {
                                "subnet_reference": {"uuid": "subnet-1"},
                                "ip_endpoint_list": [{"ip": "10.30.0.10"}],
                            }
                        ],
                    },
                },
            }
        ],
        clusters=[
            {"metadata": {"uuid": "cluster-1"}, "spec": {"name": "AHV-Cluster"}},
        ],
        subnets=[
            {"metadata": {"uuid": "subnet-1"}, "spec": {"name": "App-Net"}},
        ],
    )

    assets = snapshot.build_asset_metadata()

    assert len(assets) == 1
    asset = assets[0]
    assert asset.ip == "10.30.0.10"
    assert asset.cluster == "AHV-Cluster"
    assert asset.subnets == ["App-Net"]
    assert asset.categories == {"app": "payments"}
    assert asset.power_state == "ON"


def test_nutanix_snapshot_build_application_mappings() -> None:
    snapshot = NutanixSnapshot(
        vms=[
            {
                "metadata": {"uuid": "vm-1", "name": "vm-1"},
                "spec": {"name": "vm-1"},
                "status": {
                    "cluster_reference": {"uuid": "cluster-1"},
                    "resources": {
                        "nic_list": [
                            {
                                "subnet_reference": {"uuid": "subnet-1"},
                                "ip_endpoint_list": [{"ip": "10.30.0.10"}],
                            }
                        ]
                    },
                },
            },
            {
                "metadata": {"uuid": "vm-2", "name": "vm-2"},
                "spec": {"name": "vm-2"},
                "status": {
                    "cluster_reference": {"uuid": "cluster-1"},
                    "resources": {
                        "nic_list": [
                            {
                                "subnet_reference": {"uuid": "subnet-1"},
                                "ip_endpoint_list": [{"ip": "10.30.0.20"}],
                            }
                        ]
                    },
                },
            },
        ],
        clusters=[
            {"metadata": {"uuid": "cluster-1"}, "spec": {"name": "AHV-Cluster"}},
        ],
        subnets=[
            {"metadata": {"uuid": "subnet-1"}, "spec": {"name": "App-Net"}},
        ],
    )

    apps = snapshot.build_application_mappings()

    assert len(apps) == 1
    app = apps[0]
    assert app.name == "nutanix:AHV-Cluster"
    assert sorted(app.asset_ips) == ["10.30.0.10", "10.30.0.20"]

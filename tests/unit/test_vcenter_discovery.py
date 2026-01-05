from flowlens.discovery.vcenter import VCenterSnapshot


def test_vcenter_snapshot_build_asset_metadata() -> None:
    snapshot = VCenterSnapshot(
        vms=[
            {
                "vm": "vm-1",
                "name": "app-01",
                "guest_IP": "10.20.0.10",
                "guest_IPs": ["10.20.0.11"],
                "cluster": "domain-c7",
                "networks": ["network-42"],
                "power_state": "POWERED_ON",
            }
        ],
        clusters=[{"cluster": "domain-c7", "name": "Cluster-A"}],
        networks=[{"network": "network-42", "name": "Prod-Net"}],
        tags={"vm-1": ["tag-a", "tag-b"]},
    )

    assets = snapshot.build_asset_metadata()

    assert {asset.ip for asset in assets} == {"10.20.0.10", "10.20.0.11"}
    asset = next(asset for asset in assets if asset.ip == "10.20.0.10")
    assert asset.cluster == "Cluster-A"
    assert asset.networks == ["Prod-Net"]
    assert asset.tags == ["tag-a", "tag-b"]
    assert asset.power_state == "POWERED_ON"


def test_vcenter_snapshot_build_application_mappings() -> None:
    snapshot = VCenterSnapshot(
        vms=[
            {
                "vm": "vm-1",
                "name": "app-01",
                "guest_IP": "10.20.0.10",
                "cluster": "domain-c7",
            },
            {
                "vm": "vm-2",
                "name": "app-02",
                "guest_IP": "10.20.0.20",
                "cluster": "domain-c7",
            },
        ],
        clusters=[{"cluster": "domain-c7", "name": "Cluster-A"}],
        networks=[],
        tags={},
    )

    apps = snapshot.build_application_mappings()

    assert len(apps) == 1
    app = apps[0]
    assert app.name == "vcenter:Cluster-A"
    assert sorted(app.asset_ips) == ["10.20.0.10", "10.20.0.20"]

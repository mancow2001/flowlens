from flowlens.discovery.kubernetes import KubernetesSnapshot


def test_kubernetes_snapshot_build_asset_metadata() -> None:
    snapshot = KubernetesSnapshot(
        namespaces=[],
        pods=[
            {
                "metadata": {"name": "api", "namespace": "default", "labels": {"app": "api"}},
                "status": {"podIP": "10.0.0.10"},
            },
            {
                "metadata": {"name": "pending", "namespace": "default"},
                "status": {},
            },
        ],
        services=[
            {
                "metadata": {"name": "svc", "namespace": "default"},
                "spec": {"clusterIP": "10.0.0.20"},
            },
            {
                "metadata": {"name": "headless", "namespace": "default"},
                "spec": {"clusterIP": "None"},
            },
        ],
    )

    assets = snapshot.build_asset_metadata("prod")

    assert {asset.ip for asset in assets} == {"10.0.0.10", "10.0.0.20"}
    pod_asset = next(asset for asset in assets if asset.ip == "10.0.0.10")
    assert pod_asset.kind == "pod"
    assert pod_asset.namespace == "default"
    assert pod_asset.labels == {"app": "api"}
    service_asset = next(asset for asset in assets if asset.ip == "10.0.0.20")
    assert service_asset.kind == "service"


def test_kubernetes_snapshot_build_application_mappings() -> None:
    snapshot = KubernetesSnapshot(
        namespaces=[],
        pods=[
            {
                "metadata": {
                    "name": "api-123",
                    "namespace": "payments",
                    "labels": {"app.kubernetes.io/name": "api"},
                },
                "status": {"podIP": "10.1.0.1"},
            },
            {
                "metadata": {
                    "name": "api-456",
                    "namespace": "payments",
                    "labels": {"app.kubernetes.io/name": "api"},
                },
                "status": {"podIP": "10.1.0.2"},
            },
        ],
        services=[
            {
                "metadata": {
                    "name": "checkout",
                    "namespace": "payments",
                    "labels": {"app": "checkout"},
                },
                "spec": {"clusterIP": "10.1.0.100"},
            }
        ],
    )

    apps = snapshot.build_application_mappings("prod")
    app_names = {app.name for app in apps}

    assert "prod:payments:api" in app_names
    assert "prod:payments:checkout" in app_names

    api_app = next(app for app in apps if app.name == "prod:payments:api")
    assert sorted(api_app.asset_ips) == ["10.1.0.1", "10.1.0.2"]

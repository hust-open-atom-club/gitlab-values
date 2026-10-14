# 监控配置维护

`monitoring.yaml` 包含 GitLab、Sidekiq、CNPG、SeaweedFS、ValKey 的采集对象。
`monitoring-k3s-values.json` 是 kube-prometheus-stack 的 Helm 覆盖值，JSON 可直接作为 Helm values 使用。
`monitoring-dashboards/` 保存三个 K3s 组件面板的 ConfigMap，UID 与原面板一致。

## 当前变更

- K3s 的 Controller Manager、Scheduler、kube-proxy 指标实际位于 `job="apiserver"`。
- 三个 Down 告警监测实际组件指标缺失，保留 15 分钟等待；Helm 覆盖值禁用旧表达式并加入同名替代规则。
- 组件面板使用实际 K3s 指标；CPU、内存、goroutine 和 rest_client 指标标注为共享 K3s 进程。
- SeaweedFS Filer 通过 `monitoring: "true"` 仅抓取 filer Service，排除 filer-client 重复采集。
- Sidekiq PodMonitor 抓取已有的 `http-metrics` 端口 3807，并固定 `job="gitlab-sidekiq"` 以匹配面板。
- 未启用 Workhorse exporter、未改变备份和 ValKey 内存限制。

## 应用与升级

以下命令会修改集群，执行前确认目标为 `hoac-git`。

```powershell
kubectl --context hoac-git apply -f monitoring.yaml
kubectl --context hoac-git apply -f monitoring-dashboards/
```

后续升级 monitoring release 时，保留已有 release values 并合并 K3s 覆盖值。当前已验证的 chart 版本为 91.4.0：

```powershell
helm upgrade monitoring prometheus-community/kube-prometheus-stack --kube-context hoac-git --namespace monitoring --reuse-values --version 91.4.0 -f monitoring-k3s-values.json
kubectl --context hoac-git apply -f monitoring-dashboards/
```

升级到其他 chart/Kubernetes 版本时重新渲染并核对指标。Helm 会生成默认面板 ConfigMap，升级后需再次应用 `monitoring-dashboards/`，避免恢复默认 job。首次修复是在当前三个 PrometheusRule 上定向修改，未执行 Helm upgrade；后续升级使用上述覆盖值持久保留规则。

## 验证

Prometheus 中应有两个健康的 `up{job="gitlab-sidekiq"}` 目标，且不再有 `up{job="seaweedfs-filer-client"}`。
三个组件 Down 告警应为 inactive；对应 Grafana 面板不再使用独立 kube-controller-manager/kube-scheduler/kube-proxy job。

35 条 Grafana 管理的告警及 GitLab 面板保存在 Grafana 数据库中，应随 Grafana PVC 备份；规则直接使用“飞书告警”卡片通知。未对历史 Sidekiq dead 任务或累计错误设置存量告警，SMART exit 4 已忽略。

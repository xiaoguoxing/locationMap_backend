# 水质地图数据接口服务

独立的 Flask 接口服务，只输出 JSON / GeoJSON，不做任何服务端 HTML 渲染。
前端（`apps/web` 的 locationMap 模块）通过 Leaflet/OpenLayers 直接消费本服务的数据。

老的 `dashboard/` 服务（Flask + folium 预生成 HTML + iframe）保持原样可继续运行，
两者互不影响，便于对照验证行为一致性。

## 设计要点

**数据源可替换**：业务层只依赖 `repository.MeasurementRepository` 抽象接口，
当前实现是 `CsvMeasurementRepository`（读 `gencsv/output/*.csv`）。
将来改为直连 SQL Server 时，只需新增一个 `SqlMeasurementRepository` 并在
配置里切换，Service / Controller / 前端均无需改动。

**接口契约与 Java 后端对齐**：路径风格、统一响应包装、错误码均遵循
`.kiro/specs/springboot-backend-rewrite` 的设计，因此将来若切到 Spring Boot
后端，前端不需要任何改动。

**色阶单一来源**：判色阈值只在 `metadata.py::COLOR_SCALES` 定义一次，
既供 `/parameter/list` 对外输出，也供各视图内部计算 `colorLevel`，
保证后端着色与前端图例 100% 同源。

## 启动

```bash
# 项目根目录下（需先激活 .venv312）
python -m api.app

# 或指定端口
set WQ_API_PORT=5001 && python -m api.app
```

默认监听 `5001`（避开老 dashboard 的 5000）。

## 接口清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/water-quality/parameter/list` | 参数元数据 + 色阶规则 |
| GET | `/api/water-quality/measurement/date-ranges` | 可用日期区间清单 |
| GET | `/api/water-quality/boundary/districts` | 18 区边界（含标注锚点） |
| GET | `/api/water-quality/boundary/tpu` | 292 个 TPU 细分区边界 |
| POST | `/api/water-quality/measurement/query` | 水质数据查询（四种视图） |
| GET | `/actuator/health` | 健康检查（不套统一包装） |

## 统一响应包装

所有 `/api/**` 响应结构一致：

```json
{
  "success": true,
  "code": 200,
  "message": "",
  "data": {},
  "timestamp": 1754500000000,
  "requestId": "uuid"
}
```

## 错误码

| code | 含义 |
| --- | --- |
| 200 | 成功（含命中为零） |
| 4001 | `all_params` 仅支持 `viewType=district_all_param` 或 `tpu` |
| 4002 | `district_all_param` 仅支持 `parameter=all_params` |
| 4003 | 日期格式非法 / `dateFrom > dateTo` / 必填缺失 |
| 4004 | 日期跨度超过 90 天 |
| 4005 | 结果集超过 50000 个 Feature |
| 404 | 请求的资源不存在（如未生成对应 CSV） |
| 500 | 服务端异常（message 已脱敏） |

## 鉴权

当前默认关闭（对齐内网现状）。扩展位见 `api/security.py`：
把 `WQ_API_AUTH_ENABLED` 设为 `true` 即启用 Bearer Token 校验，
业务代码无需改动。

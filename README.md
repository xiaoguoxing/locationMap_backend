# 香港水质地图数据服务

> 本文是项目唯一维护文档，供开发人员、运维人员和后续 AI 模型使用。更新日期：2026-08-12。

## 1. 项目边界

项目由两个工作区组成：

- Python 数据与 API：`hkLocatingMap/`
- React 地图前端：`HK_WQMS_web/`

后端统一使用 Python。Java 后端、旧 Folium 地图生成器和旧 iframe Dashboard 已删除，不应恢复为并行实现。团队主要维护者是前端程序员，因此后端应保持结构简单、配置明确、可独立验证。

## 2. 当前架构

```text
业主内网 LIMS SQL Server
  ↓ gencsv/date_range_runner.py（人工或计划任务触发）
gencsv/output/*.csv
  ↓ CsvMeasurementRepository
Flask API（5001，JSON / GeoJSON）
  ↓ /api/water-quality/*
React + TypeScript + OpenLayers
  ↓
香港 18 区 / 292 个 TPU 地图
```

当前 CSV 是过渡数据源。目标方向是 Python API 使用只读账号直连业主 SQL Server；本地无法访问内网时继续使用 CSV 开发。数据访问层保留 `MeasurementRepository` 抽象，后续新增 `SqlMeasurementRepository`，不改变 Service、接口契约和前端调用。

## 3. 目录结构

```text
api/
  app.py              Flask 入口
  config.py           环境变量配置
  repository.py       数据源抽象与 CSV 实现
  service.py          四类视图聚合
  geography.py        18 区、TPU、空间归属
  geo_utils.py        区名及标注锚点算法
  metadata.py         参数与色阶唯一来源
  data/               API 运行时地理数据
gencsv/               SQL Server → CSV 抽取
tools/                TPU 下载、18 区海岸线裁剪
01_extract_csv.bat   Windows CSV 抽取入口
```
## 4. 安装与配置

```cmd
py -3.12 -m venv .venv312
.venv312\Scripts\python.exe -m pip install --upgrade pip
.venv312\Scripts\python.exe -m pip install -r requirements.txt
```

复制 `gencsv/setting.ini.example` 为 `gencsv/setting.ini`，填写 SQL Server 只读连接信息。该文件包含数据库凭据，已被 Git 排除，禁止提交。

主要环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `WQ_API_HOST` | `0.0.0.0` | API 监听地址 |
| `WQ_API_PORT` | `5001` | API 端口 |
| `WQ_API_DATA_SOURCE` | `csv` | 数据源类型 |
| `WQ_API_CSV_DIR` | `gencsv/output` | CSV 目录 |
| `WQ_API_GEO_DATA` | `api/data` | 地理数据目录 |
| `WQ_API_CORS_ORIGINS` | 本地 9527 | 允许的前端来源 |
| `WQ_API_AUTH_ENABLED` | `false` | 是否启用 Bearer Token |

## 5. 数据来源与 CSV 抽取

正式水质数据来自业主内网 LIMS 的 Microsoft SQL Server。当前通过 `pyodbc` 使用只读账号执行 `gencsv/sqltemplate/` 中三套 SQL 模板：

| 参数 | 代码 | 单位 |
| --- | --- | --- |
| 游离余氯 | `CL2_FREE_1` | mg/L |
| 大肠杆菌 | `ECOLI` | CFU/100mL |
| 浑浊度 | `TURBY` | NTU |

SQL 会按日期、样本状态、数值有效性和采样点编码过滤数据。

无参数时生成最近 30 天的 7 天滑动窗口：

```cmd
01_extract_csv.bat
```

也可指定日期：

```cmd
01_extract_csv.bat --from 2026-04-01 --to 2026-04-30 --range-days 7
```

输出文件规则：

```text
{parameter}_{dateFrom}_{dateTo}_{timestamp}.csv
```

重复抽取不会覆盖旧文件；同参数、同日期区间有多份时，API 使用文件名时间戳最新的一份。`gencsv/output/` 不进入 Git，部署时必须在业主服务器生成或通过受控方式同步。
## 6. 启动与接口

开发启动：

```cmd
.venv312\Scripts\python.exe -m api.app
```

默认地址：`http://127.0.0.1:5001`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/water-quality/parameter/list` | 参数与色阶元数据 |
| GET | `/api/water-quality/measurement/date-ranges` | 可用 CSV 日期区间 |
| GET | `/api/water-quality/boundary/districts` | 18 区边界与标注锚点 |
| GET | `/api/water-quality/boundary/tpu` | 292 个 TPU 边界 |
| POST | `/api/water-quality/measurement/query` | 水质数据查询 |
| GET | `/actuator/health` | 健康检查 |

查询视图：`district`、`detailed`、`district_all_param`、`tpu`。

统一响应字段：`success`、`code`、`message`、`data`、`timestamp`、`requestId`。

API 数据处理包括：读取和规整 CSV、邻里名称归一化、18 区聚合、TPU 空间归属、色阶计算及 GeoJSON 组装。

## 7. 地图业务规则

- zoom `< 13` 显示香港 18 区。
- zoom `>= 13` 显示 292 个 TPU。
- 18 区与 TPU 图层互斥。
- 参数包括 `cl2_free_1`、`ecoli`、`turby`、`all_params`。
- TPU 查询一次返回三个参数；前端切换参数时不重新请求同日期 TPU 数据。
- TPU 单参数弹窗只显示当前参数，全部参数模式显示三个参数。
- 无数据区域使用普通灰色。
- 18 区边界已按 TPU 陆地轮廓裁掉海域。
- 前端支持简体中文、繁体中文和英文。

前端关键路径：

- `apps/web/src/views/locationMap/components/MyMap.tsx`
- `apps/web/src/views/locationMap/components/MapControls.tsx`
- `apps/web/src/views/locationMap/components/MapPopup.tsx`
- `apps/web/src/views/locationMap/map/buildLayers.ts`
- `apps/web/src/api/modules/locationMap.ts`
- `apps/web/vite.config.ts`
## 8. 地理数据维护

运行时资源位于 `api/data/`：

- `hk_districts.geojson`：已裁掉海域的香港 18 区边界。
- `hk_tpu_simplified.geojson`：来自香港 CSDI 规划署 OGC WFS 的 292 个 TPU。
- `district_mapping.py`：邻里名称到行政区的映射。

更新 TPU：

```cmd
.venv312\Scripts\python.exe tools\fetch_tpu_boundary.py
```

重新裁剪 18 区海域：

```cmd
.venv312\Scripts\python.exe tools\clip_district_coastline.py
```

工具仅在边界更新时运行，API 日常启动不需要联网。

## 9. 当前限制与后续直连 SQL Server

CSV 只能查询已生成的日期区间，不支持真正任意日期；滑动窗口还存在重复数据。正式直连数据库前需确认：

1. SQL Server 版本及只读账号或只读视图。
2. 表结构、唯一键和更新时间字段。
3. 任意日期查询的跨度、超时和并发限制。
4. 历史趋势与 AI 预测是否允许直接查询业务库。

实现时新增 `SqlMeasurementRepository`，并在业主内网测试环境验证数据一致性和性能。若大量历史分析会影响业务库，再评估同步到独立查询数据库。

前端当前使用固定日期区间下拉框；数据库支持任意日期后，应改为起止日期选择器，并按视图限制查询跨度和聚合粒度。

## 10. 生产部署与安全

- `python -m api.app` 仅用于开发。
- Windows 生产使用 Waitress，Linux 使用 Gunicorn。
- API 建议仅监听 `127.0.0.1:5001`，由 Nginx/IIS 将 `/api/water-quality/` 原样代理，并对外提供 HTTPS。
- 数据库账号必须只读，优先只授权指定视图。
- 当前鉴权默认关闭，仅适用于受控内网；公网开放前必须启用鉴权或网关限制。
- Git 不包含 `.venv312`、`gencsv/setting.ini`、CSV 产物和日志。
- AI 不主动执行远程 push。

## 11. 验证基线

目录整合后已验证：

- 参数元数据：4 个。
- CSV 日期区间：15 个。
- 行政区边界：18 个。
- TPU 边界：292 个。
- `2026-04-24` 至 `2026-04-30` 查询要素数：`district=14`、`detailed=27`、`district_all_param=14`、`tpu=15`。
- `/actuator/health` 返回 `200` 与 `{"status":"UP"}`。

上述数字是当前样例 CSV 的历史基线。每次修改后必须重新执行验证，不能仅凭该记录声明通过。

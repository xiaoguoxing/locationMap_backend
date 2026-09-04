# 香港水质地图数据服务

> 本文是项目唯一维护文档，供开发人员、运维人员和后续 AI 模型使用。更新日期：2026-08-13。

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
  extraction.py       进程内后台同步任务
  repository.py       数据源抽象与 CSV 实现
  service.py          四类视图聚合
  geography.py        18 区、TPU、空间归属
  geo_utils.py        区名及标注锚点算法
  metadata.py         参数与色阶唯一来源
  data/               API 运行时地理数据
gencsv/
  extraction_service.py  批处理与 API 共用的抽取、暂存和发布逻辑
  date_range_runner.py   CSV 抽取命令行入口
  sqltemplate/           三项水质参数 SQL 模板
tools/                TPU 下载、18 区海岸线裁剪
01_extract_csv.bat    Windows CSV 抽取入口
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
| `WQ_API_DATA_SOURCE` | `csv` | 数据源类型；当前已实现 `csv`，规划增加 `fixture`、`sqlserver` |
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

### 5.1 查询模式

**默认模式（7天滚动窗口）**：

```cmd
01_extract_csv.bat
```

最近 30 天，每天生成一个 7 天窗口，共 31 个区间 × 3 个参数 = **93 次查询**。

**按周模式（推荐）**：

```cmd
01_extract_csv.bat --weekly
```

按自然周（周一到周日）分组，最近 30 天约 5 个周 × 3 个参数 = **15 次查询**，减少 **84%** 查询次数。

**指定日期**：

```cmd
01_extract_csv.bat --from 2026-04-01 --to 2026-04-30 --weekly
```

输出文件规则：

```text
{parameter}_{dateFrom}_{dateTo}_{timestamp}.csv
```

重复抽取不会覆盖旧文件。批处理与 API 同步共用 `gencsv/extraction_service.py`：所有查询先写入 `gencsv/output/.staging/`，全部成功后才发布到 `gencsv/output/releases/{releaseId}/`；任一查询失败会清理暂存目录，不删除或覆盖原有 CSV。Repository（数据仓储层）同时兼容历史根目录 CSV 和带完整 `manifest.json` 的新发布批次，同参数、同日期区间使用文件名时间戳最新的一份。`gencsv/output/` 不进入 Git，部署时必须在业主服务器生成或通过受控方式同步。

### 5.2 前端隐藏同步入口

地图页默认不显示同步按钮。按 `Ctrl + Alt + Shift + S` 可在当前页面会话内切换显示或隐藏，未使用 URL Query（查询参数）。

按钮调用：

```text
POST /api/water-quality/extraction/refresh
```

该接口固定执行与 `01_extract_csv.bat` 无参数运行相同的任务：最近 30 天、7 天滚动窗口，共 31 个日期区间 × 3 项参数，约 93 次 SQL Server 查询。前端只提交后台任务并显示提交结果，不轮询状态、不刷新 React Query（请求缓存）、不切换日期、不重建当前地图。新数据在用户下次刷新或重新进入页面后进入日期列表。

**优化建议**：生产环境可修改 API 使用 `--weekly` 模式，将查询次数减少到约 15 次（84% 减少）。

隐藏入口不是权限控制。生产环境仍需通过真实登录鉴权、IIS/Nginx 限制或受控内网访问保护同步接口，不能依靠组合键保密。
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
| POST | `/api/water-quality/extraction/refresh` | 创建后台 CSV 同步任务 |
| GET | `/api/water-quality/extraction/status?taskId=xxx` | 查询当前 API 进程内的同步任务状态 |
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
- TPU 单参数模式：标记和弹窗只显示当前选中的参数。
- TPU 全部参数模式（`all_params`）：标记和弹窗同时显示三个参数（游离余氯、大肠杆菌、浑浊度）。
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

### 8.1 18 区边界裁剪优化

裁剪脚本采用多轮几何清理策略，解决原始数据的问题：

**优化目标**：
1. 移除 TPU 拼接产生的内部白色条纹
2. 消除边界杂质、碎片和毛刺
3. 简化轮廓，减少文件体积

**清理流程**：
1. 用 292 个 TPU 并集构建陆地轮廓
2. 多轮缓冲操作：正向填充缝隙 → 负向移除细条 → 正向恢复平滑
3. Douglas-Peucker 算法简化轮廓
4. 过滤面积过小的碎片

**关键参数**（位于 `tools/clip_district_coastline.py`）：

```python
SIMPLIFY_TOLERANCE = 0.0002   # 简化容差（约 22 米）
MIN_AREA_RATIO = 0.005        # 最小面积比（0.5%）
BUFFER_DISTANCE = 0.0001      # 正向缓冲（约 11 米）
NEGATIVE_BUFFER = -0.00015    # 负向缓冲（约 16 米）
```

**优化效果**：
- 文件大小：645 KB → 281 KB（↓ 56%）
- 总顶点数：~20,900 → ~7,810（↓ 63%）
- 面积保持率：98.4%
- 白色条纹和杂质显著减少

**参数调优**：
- 白色条纹仍明显 → 增大 `BUFFER_DISTANCE` 和 `NEGATIVE_BUFFER` 绝对值
- 边界过于粗糙 → 减小 `SIMPLIFY_TOLERANCE`
- 小岛屿消失 → 减小 `MIN_AREA_RATIO`
- 边界明显偏移 → 减小所有缓冲参数

详细技术说明见 `tools/CLIP_IMPROVEMENT.md`。

## 9. 数据源演进与任意日期方案

### 9.1 当前已实现：CSV 数据源

当前 `WQ_API_DATA_SOURCE=csv`，地图只查询已生成的日期区间。方案一已保留：人工、计划任务或前端隐藏按钮均可触发 SQL Server → CSV，同步失败不影响现有地图数据。

### 9.2 规划：三种可切换数据源

数据访问层继续统一实现 `MeasurementRepository`，通过启动环境变量选择：

| 值 | 使用环境 | 定位 | 当前状态 |
| --- | --- | --- | --- |
| `csv` | 本地开发、历史兼容、生产兜底 | 读取现有 CSV 和完整发布批次 | 已实现 |
| `fixture` | 本地开发任意日期交互 | 使用少量脱敏固定测试数据模拟查询 | 待实现 |
| `sqlserver` | 业主内网服务器 | 使用只读账号直接查询 LIMS SQL Server | 待实现 |

Windows 启动示例：

```cmd
set WQ_API_DATA_SOURCE=csv
.venv312\Scripts\python.exe -m api.app
```

正式环境切换示例：

```cmd
set WQ_API_DATA_SOURCE=sqlserver
.venv312\Scripts\python.exe -m api.app
```

环境变量在 API 启动时读取，修改后必须重启 5001 服务。新增的 `FixtureMeasurementRepository` 和 `SqlServerMeasurementRepository` 必须返回与 CSV 仓储相同的统一字段：`sampleNo`、`locationCode`、`locationDesc`、`district`、`collectedAt`、`owner`、`latitude`、`longitude`、`value`。因此 Service（业务层）、地图接口、18 区聚合和 TPU 空间归属不应随数据源切换而重写。

### 9.3 SQL Server 直连已知基础

现有 SQL 模板已经明确使用 `sample`、`suserflds`、`result` 三张表，通过 `sampno` 关联，并查询 `CL2_FREE_1`、`ECOLI`、`TURBY` 三项参数。`gencsv/setting.ini` 已保存部署环境的连接配置，业主服务器已安装 `ODBC Driver 18 for SQL Server`。这些信息足以实现当前地图所需的直连仓储，无需掌握整个 LIMS 数据库结构。

直连实现必须：

1. 使用参数化查询，不拼接前端输入的 SQL、日期、文件路径或命令。
2. 修正结束日期边界，使用“开始日期大于等于、结束日期次日小于”的半开区间，覆盖结束日全天。
3. 处理现有 `TOP 1000` 截断和三套 SQL 规则不一致的问题。
4. 配置最大日期跨度、连接超时、查询超时和并发限制。
5. 数据库账号保持只读，优先只授权指定视图。

### 9.4 任意日期查询与本地开发

前端改为起止日期选择器后，不要求开发机安装本地 SQL Server。空数据库无法模拟业主的真实表结构、索引、数据分布和性能，本地继续使用 `csv` 验证现有地图，使用 `fixture` 验证任意日期交互、参数校验、空数据和错误提示。

本地可验证：

- 起止日期选择和最大跨度校验。
- 四类视图的接口结构及地图渲染。
- 无数据、非法日期和请求失败提示。
- 前端请求缓存与图层刷新逻辑。

业主内网环境必须验证：

- 表字段、关联及结果与现有 CSV 是否一致。
- 只读账号权限、网络和 ODBC 驱动。
- 查询耗时、超时、并发和业务库压力。
- 移除 `TOP 1000` 后的真实结果规模。

### 9.5 待业主确认

在开放任意日期查询前需确认：

1. 页面请求是否允许直接查询业务库。
2. 各视图允许的最大日期跨度、超时时间和并发数。
3. LIMS 数据“完成”的状态字段及当天数据是否允许查询。
4. 历史趋势和 AI 预测是否允许直接查询业务库。

若大量历史分析会影响业务库，再评估同步到独立查询数据库。SQL Server 模式下隐藏同步按钮仍可保留，用于生成 CSV 备份或故障兜底，但不再是地图获取最新数据的必经步骤。

## 10. 生产部署与安全

- `python -m api.app` 仅用于开发。
- Windows 生产使用 Waitress，Linux 使用 Gunicorn。
- 当前后台同步任务状态保存在 API 进程内；前端不轮询状态，因此当前交互不受影响。若以后启用状态轮询或多进程部署，需要将任务状态迁移到共享存储或使用独立任务队列。
- 业主 Windows 服务器已安装 `ODBC Driver 18 for SQL Server`；其他部署环境需单独安装。`pyodbc` 是 Python 依赖，ODBC Driver 是操作系统驱动，两者缺一不可。
- API 建议仅监听 `127.0.0.1:5001`，由 Nginx/IIS 将 `/api/water-quality/` 原样代理，并对外提供 HTTPS。
- 数据库账号必须只读，优先只授权指定视图。
- 当前鉴权默认关闭，仅适用于受控内网；公网开放前必须启用鉴权或网关限制。
- Git 不包含 `.venv312`、`gencsv/setting.ini`、CSV 产物和日志。
- AI 不主动执行远程 push。

## 11. 验证基线

目录整合后已验证：

- 参数元数据：4 个。
- CSV 日期区间：15 个。
- 行政区边界：18 个（MultiPolygon: 5, Polygon: 13）。
- 行政区总顶点数：约 7,810（优化后）。
- TPU 边界：292 个。
- `2026-04-24` 至 `2026-04-30` 查询要素数：`district=14`、`detailed=27`、`district_all_param=14`、`tpu=15`。
- `/actuator/health` 返回 `200` 与 `{"status":"UP"}`。

上述数字是当前样例 CSV 的历史基线。每次修改后必须重新执行验证，不能仅凭该记录声明通过。

**边界优化历史**：
- 2026-08: 重新裁剪 18 区，采用多轮缓冲清理，文件从 645 KB 降至 281 KB，顶点数减少 63%，内部条纹和杂质显著改善。

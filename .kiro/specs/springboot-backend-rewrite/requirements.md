# Requirements Document

## Introduction

本需求面向"将现有 Python (Flask + folium + 独立 gencsv 脚本) 后端整体重写为 Java SpringBoot 后端"。重写后的后端承担三件事：

1. 接管 `gencsv/` 模块的数据采集职责（直接从上游数据库取水质 / 黑点数据，参数化执行原有 SQL 模板），不再保留独立 Python 工具。
2. 以**只输出 GeoJSON / JSON 数据接口**的形式（方案 B）取代原 Flask + folium 的"服务端预生成 Leaflet HTML + iframe 嵌入"模式，前端改用 Leaflet.js 直接渲染。
3. 提供参数元数据接口（`display_name` / `unit` / 色阶规则），把原 `cluster_map.py::get_color` 的阈值规则与 `dashboard.html` Legend 色阶规则规范化、单一来源化。

历史已生成的 `maps/output/{district,detailed,district_all_param}/*.html` 不再服务，新后端不兼容旧 `/maps/output/*` 路由。持久层使用 MyBatis（保留原 SQL 灵活性）。前后端分离部署。

所有 API 路径与响应包装遵循全局《接口设计规范》：路径风格 `/api/{module}/{?resource}/{action}`、统一响应包装（`success` / `code` / `message` / `data` / `timestamp` / `requestId`）、分页结构沿用 MyBatis-Plus 风格、参数命名 camelCase。

目标部署 OS：Linux；后端默认监听端口 5000。

## Glossary

- **SpringBoot_Backend**：本次重写产出的 Java SpringBoot 后端服务整体。
- **Water_Quality_Service**：SpringBoot_Backend 中负责水质参数测量数据查询的业务模块。
- **Blackspot_Service**：SpringBoot_Backend 中负责黑点数据查询的业务模块。
- **Parameter_Metadata_Service**：SpringBoot_Backend 中负责输出参数元数据（显示名 / 单位 / 色阶规则）的业务模块。
- **Data_Extraction_Module**：SpringBoot_Backend 中接管原 `gencsv/` 职责的子模块，负责执行 SQL 模板、按日期范围参数化查询、批量归档为 CSV。
- **Persistence_Layer**：SpringBoot_Backend 的 MyBatis 持久层。
- **Source_Database**：上游水质 LIMS 数据库（现有 `setting.ini` 指向 SQL Server `labworks` / `labworks_wsduat`，端口 `1433`）；本系统通过 ≥2 个独立数据源连接配置承载水质与黑点等不同业务库。
- **Frontend_Client**：基于 Leaflet.js 的前端单页应用，独立于 SpringBoot_Backend 部署。
- **Parameter_Code**：水质参数代码，取值集合 `{cl2_free_1, ecoli, turby, all_params}`。
- **View_Type**：地图视图类型，取值集合 `{district, detailed, district_all_param}`。
  - `district`：按行政区聚合，每区一个代表点（坐标来自 `district_gps.csv`）。
  - `detailed`：按测点逐点显示，使用各测点自身坐标。
  - `district_all_param`：按行政区聚合，同一区同时承载所有参数的统计结果（仅 `parameter = all_params` 使用此视图）。
- **District_GPS**：行政区中心点坐标表，来自原 `gencsv/missing_gps/district_gps.csv`，用于 `viewType = district` / `district_all_param` 时输出的 Feature 几何坐标。
- **Date_Range**：闭区间日期范围 `[date_from, date_to]`，两端均为 `YYYY-MM-DD`。
- **Color_Scale**：以阈值区间映射颜色等级的规则集合，每个 Parameter_Code 对应一套 Color_Scale。
- **API_Response_Wrapper**：统一响应包装，含字段 `success`、`code`、`message`、`data`、`timestamp`、`requestId`。
- **GeoJSON**：RFC 7946 定义的地理数据格式；本系统对外只输出 `FeatureCollection`，每个 `Feature.geometry` 类型为 `Point`。
- **WGS84**：经纬度坐标参考系（与原 folium / Leaflet 行为一致）。

## Requirements

### Requirement 1: 水质参数测量数据查询

**User Story:** 作为前端 Leaflet 地图应用，我需要通过单个 HTTP 接口按"参数 + 日期范围 + 视图类型"获取水质测量数据的 GeoJSON，以便直接在 Leaflet 上渲染散点 / 聚合标记，不依赖任何服务端预生成的 HTML。

#### Acceptance Criteria

1. THE Water_Quality_Service SHALL 暴露 `POST /api/water-quality/measurement/query` 接口，请求体为 JSON，包含字段 `parameter`（取自 Parameter_Code）、`dateFrom`（`YYYY-MM-DD`）、`dateTo`（`YYYY-MM-DD`）、`viewType`（取自 View_Type）。
2. WHEN 请求中 `parameter ∈ {cl2_free_1, ecoli, turby}` 且 `viewType ∈ {district, detailed}`，THE Water_Quality_Service SHALL 返回 GeoJSON `FeatureCollection`，其中每个 `Feature.geometry.type` 为 `Point`、`coordinates` 顺序为 `[longitude, latitude]`、坐标参考系为 WGS84，且经纬度数值精度保留小数点后 6 位。
3. WHEN `viewType = district`，THE Water_Quality_Service SHALL 按 District 聚合测点，每个 District 输出 1 个 Feature，其 `geometry.coordinates` 取自 District_GPS 中对应区的中心点；`properties` 至少包含字段 `district`（区名，非空字符串）、`parameter`（Parameter_Code）、`avgValue`（数值，保留小数点后 2 位）、`maxValue`（数值，保留小数点后 2 位）、`minValue`（数值，保留小数点后 2 位）、`sampleCount`（非负整数）、`colorLevel`（字符串等级标签）。
4. WHEN `viewType = detailed`，THE Water_Quality_Service SHALL 输出每条原始采样记录为 1 个 Feature，并在 `properties` 中至少包含字段 `sampleNo`（字符串）、`locationCode`（字符串）、`locationDesc`（字符串）、`collectedAt`（`YYYY-MM-DDTHH:mm:ss`，时区固定为 Asia/Hong_Kong，+08:00）、`parameter`（Parameter_Code）、`value`（数值，保留小数点后 2 位）、`unit`（字符串）、`colorLevel`（字符串等级标签）。
5. WHEN `parameter = all_params` 且 `viewType = district_all_param`，THE Water_Quality_Service SHALL 返回 GeoJSON `FeatureCollection`，每个 District 输出 1 个 Feature，其 `properties` 包含字段 `district`（区名，非空字符串），并对每个 Parameter_Code 输出独立子对象（子对象的键名为 Parameter_Code 字符串字面量，即 `cl2_free_1` / `ecoli` / `turby`），每个子对象至少含 `avgValue`（数值，保留小数点后 2 位）与 `colorLevel`（字符串等级标签）。
6. IF 请求中 `parameter = all_params` 且 `viewType ∈ {district, detailed}`，THEN THE Water_Quality_Service SHALL 拒绝该请求，返回 `code = 4001`、`message = "all_params only supports viewType=district_all_param"`。
7. IF 请求中 `parameter ∈ {cl2_free_1, ecoli, turby}` 且 `viewType = district_all_param`，THEN THE Water_Quality_Service SHALL 拒绝该请求，返回 `code = 4002`、`message = "viewType=district_all_param only supports parameter=all_params"`。
8. IF 请求中 `dateFrom`/`dateTo` 不符合 `YYYY-MM-DD` 格式、或 `dateFrom > dateTo`（任一条件成立即拒绝），THEN THE Water_Quality_Service SHALL 立即拒绝该请求，返回 `code = 4003`、`message` 中明确指出第一个失败的字段。
9. IF 请求中 `dateTo - dateFrom > 90` 天，THEN THE Water_Quality_Service SHALL 拒绝该请求，返回 `code = 4004`、`message = "Date range exceeds 90 days"`。
10. IF 查询命中的原始采样记录的 `latitude` / `longitude` 字段为空、非数值或不在 `latitude ∈ [-90, 90]` / `longitude ∈ [-180, 180]` 范围内，THEN THE Water_Quality_Service SHALL 在结果中剔除该记录，并在响应 `data.meta.droppedInvalidCoordinateCount` 中累加该计数。
11. WHEN 命中数据为零，THE Water_Quality_Service SHALL 返回 `code = 200` 且 `data.features` 为空数组（不视为错误）。
12. THE Water_Quality_Service SHALL 在响应统一包装 `{ success, code, message, data, timestamp, requestId }` 的 `data.meta` 中包含字段 `parameter`、`dateFrom`、`dateTo`、`viewType`、`featureCount`、`droppedInvalidCoordinateCount`、`queryDurationMs`，其中 `featureCount` 等于 `data.features` 数组长度，且 `featureCount` / `droppedInvalidCoordinateCount` / `queryDurationMs` 均为非负整数。
13. IF 服务端在剔除无效坐标后即将输出的 Feature 数量 > 50000，THEN THE Water_Quality_Service SHALL 拒绝该请求，返回 `code = 4005`、`message = "Result set exceeds 50000 features; please narrow date range"`。

### Requirement 2: 黑点（Blackspot）数据查询

**User Story:** 作为前端 Leaflet 地图应用，我需要通过 HTTP 接口获取黑点（卫生黑点 / 投诉黑点）数据的 GeoJSON，以便在地图上以独立图层叠加显示。

#### Acceptance Criteria

1. THE Blackspot_Service SHALL 暴露 `POST /api/water-quality/blackspot/query` 接口，请求体为 JSON，包含字段 `dateFrom`（`YYYY-MM-DD`）、`dateTo`（`YYYY-MM-DD`）。
2. WHEN 请求通过字段必填校验、`YYYY-MM-DD` 格式校验、`dateFrom <= dateTo` 校验与跨度上限校验，THE Blackspot_Service SHALL 返回 GeoJSON `FeatureCollection`（包裹在统一响应包装 `{ success, code, message, data, timestamp, requestId }` 中），其中每个 `Feature.geometry.type` 为 `Point`、`coordinates` 顺序为 `[longitude, latitude]`、经纬度数值精度保留小数点后 6 位，`properties` 包含字段 `caseId`（字符串）、`locationDesc`（字符串）、`reportDate`（`YYYY-MM-DD`）。
3. IF 请求中 `dateFrom`/`dateTo` 缺失、为空、不符合 `YYYY-MM-DD` 格式、或 `dateFrom > dateTo`（任一条件成立即拒绝），THEN THE Blackspot_Service SHALL 立即拒绝该请求，返回 `code = 4003`、`message` 中明确指出第一个失败的字段。
4. IF 请求中 `dateTo - dateFrom > 366` 天，THEN THE Blackspot_Service SHALL 拒绝该请求，返回 `code = 4004`、`message = "Date range exceeds 366 days"`。
5. IF 命中的黑点记录中 `latitude` / `longitude` 字段为空、非数值或不在 `latitude ∈ [-90, 90]` / `longitude ∈ [-180, 180]` 范围内，THEN THE Blackspot_Service SHALL 剔除该记录,并在 `data.meta.droppedInvalidCoordinateCount` 中累加该计数。
6. WHEN 命中数据为零，THE Blackspot_Service SHALL 返回 `code = 200` 且 `data.features` 为空数组。
7. THE Blackspot_Service SHALL 在 `data.meta` 中包含字段 `dateFrom`（字符串）、`dateTo`（字符串）、`featureCount`（非负整数，等于 `data.features` 数组长度）、`droppedInvalidCoordinateCount`（非负整数）、`queryDurationMs`（非负整数）。
8. THE Blackspot_Service SHALL 保证从 Controller 入口到响应序列化完成的耗时 ≤ 5000 毫秒。

> 备注：水质（R1）与黑点（R2）的同图层叠加为前端纯客户端能力，后端两个接口相互独立、不感知叠加场景。

### Requirement 3: 参数元数据与色阶规则

**User Story:** 作为前端 Leaflet 地图应用与图例渲染逻辑，我需要从单一来源拿到所有参数的显示名、单位、色阶阈值与颜色，以避免在前端硬编码（原 `cluster_map.py::get_color` 与 `dashboard.html` Legend 各持一套并相互不一致）。

#### Acceptance Criteria

1. THE Parameter_Metadata_Service SHALL 暴露 `GET /api/water-quality/parameter/list` 接口，该接口不接受任何 query parameter、path variable 或 request body。
2. WHEN `GET /api/water-quality/parameter/list` 接口被调用，THE Parameter_Metadata_Service SHALL 返回成功响应，响应体遵循项目统一响应包装结构，其业务数据部分为 JSON 数组且至少包含 4 个元素（分别对应 Parameter_Code 为 `cl2_free_1`、`ecoli`、`turby`、`all_params` 的条目），每个元素至少包含字段 `parameter`（Parameter_Code，非空字符串）、`displayName`（非空字符串）、`unit`（字符串，无单位时为空字符串）、`colorScale`（非空数组）。
3. THE Parameter_Metadata_Service SHALL 在 `colorScale` 字段中输出按 `min` 升序排列的有序数组（`min` 为 null 视为负无穷，排在数组最前），每个元素至少包含字段 `level`（非空字符串等级标签）、`color`（HEX 颜色字符串，含 `#` 前缀，长度 7 字符）、`min`（数值，含端点；null 表示负无穷）、`max`（数值，不含端点；null 表示正无穷）、`description`（字符串）。
4. THE Parameter_Metadata_Service SHALL 对 `cl2_free_1` 输出与 `dashboard.html` Legend 一致语义的 5 级色阶，**区间连续无间隙且覆盖 (-∞, +∞)**，端点处理如下：`value < 0.2 → Insufficient`、`0.2 ≤ value ≤ 1.5 → Satisfactory`、`1.5 < value ≤ 2.0 → Slightly High`、`2.0 < value ≤ 3.0 → High`、`value > 3.0 → Very High`。Legend 文字仍按原表述 `0.2 – 1.5` / `1.6 – 2.0` 等显示给用户，但后端着色判定 SHALL 严格按上述连续区间执行。本需求以 Legend 为准、废弃 `cluster_map.py::get_color` 的 `≤0.5/1.0/1.5/2.0` 阈值。
5. THE Parameter_Metadata_Service SHALL 对 `ecoli` 输出 2 级色阶，**区间连续无间隙且覆盖 (-∞, +∞)**：`value ≤ 0 → Satisfactory`、`value > 0 → Unsatisfactory`。
6. THE Parameter_Metadata_Service SHALL 对 `turby` 输出 4 级色阶，**区间连续无间隙且覆盖 (-∞, +∞)**：`value ≤ 1.5 → Satisfactory`、`1.5 < value ≤ 3.0 → Slightly High`、`3.0 < value ≤ 10.0 → High`、`value > 10.0 → Very High`。
7. THE Parameter_Metadata_Service SHALL 对 `all_params` 输出聚合元数据条目，其 `colorScale` 字段为按以下固定顺序拼接的数组：先放入 `cl2_free_1` 的 5 个色阶元素，其次放入 `ecoli` 的 2 个色阶元素，最后放入 `turby` 的 4 个色阶元素，共计 11 个元素，且每个元素的 `level`、`color`、`min`、`max`、`description` 字段值与对应子参数色阶定义完全一致（即同源复用，不允许重新定义）。
8. WHEN Water_Quality_Service 计算 Feature 的 `colorLevel` 字段且该 Feature 的参数测量值为有效数值（非 null 且非 NaN），THE Water_Quality_Service SHALL 使用 Parameter_Metadata_Service 提供的 `colorScale.level`（按测量值落入的 `min`/`max` 区间匹配）作为该字段值，确保后端着色与前端图例 100% 同源。
9. IF Water_Quality_Service 处理的 Feature 参数测量值为 null、NaN 或字段缺失，THEN THE Water_Quality_Service SHALL 将该 Feature 的 `colorLevel` 字段值设为 null，并保留 Feature 其余字段不变，不抛出异常或丢弃该 Feature。

### Requirement 4: 数据采集模块（接管 gencsv 职责）

**User Story:** 作为运维与数据负责人，我需要新后端能直接执行原 `gencsv/sqltemplate/*.sql` 模板（含 `[date_from]` / `[date_to]` 占位符）取数，不再保留独立 Python 脚本；同时保留按日期切片批量预查（用于回填 / 归档）的能力，触发方式从命令行改为 HTTP 接口手动触发。

#### Acceptance Criteria

1. THE Data_Extraction_Module SHALL 通过 Persistence_Layer 直接对 Source_Database 执行水质 / 黑点查询，且不依赖任何 CSV 中间文件作为查询数据源。
2. THE Data_Extraction_Module SHALL 把原 `gencsv/sqltemplate/*.sql` 中的 `[date_from]` / `[date_to]` 占位符迁移为 MyBatis 参数绑定（命名参数或 `#{}` 占位符），且 SHALL NOT 使用字符串拼接传入日期。
3. THE Data_Extraction_Module SHALL 暴露 `POST /api/water-quality/extraction/archive` 接口，请求体含字段 `parameter`（取自 Parameter_Code）、`dateFrom`（`YYYY-MM-DD`）、`dateTo`（`YYYY-MM-DD`）、`rangeDays`（每片窗口天数，1–365 的整数）、`stepDays`（步长，1–365 的整数，默认 1）；接口同步返回归档任务编号，同步响应耗时 ≤ 5 秒，归档执行异步进行。
4. IF 第 3 条接口的请求参数缺失、超出取值范围或不符合格式，THEN THE Data_Extraction_Module SHALL 同步返回错误响应（套用统一响应包装、`code = 4xxx`、`message` 指出第一个失败的字段），且 SHALL NOT 启动归档任务。
5. THE Data_Extraction_Module SHALL 把每片窗口的查询结果落到归档存储（默认相对路径 `./archive/`，最终形态由设计阶段决定 CSV 文件 / 数据库表），文件命名沿用原约定 `{parameter}_{dateFrom}_{dateTo}_{timestamp}.csv`，其中 `{timestamp}` 格式固定为 `yyyyMMdd_HHmmss`（与原 `gencsv/output/*.csv` 命名一致）。
6. THE Data_Extraction_Module SHALL 暴露 `GET /api/water-quality/extraction/archive/detail/{taskId}` 接口，返回字段 { 任务状态（取值固定 5 种：`PENDING` / `RUNNING` / `SUCCESS` / `PARTIAL_SUCCESS` / `FAILED`）、成功片数、失败片数、产物清单 }；产物清单中每个产物含字段 { `dateFrom`、`dateTo`、存储路径或标识、片状态（同上 5 种）、命中行数（非负整数）、耗时（毫秒，非负整数）}。
7. IF 归档过程中某片窗口执行失败，THEN THE Data_Extraction_Module SHALL 记录错误条目（含字段 { `parameter`、`dateFrom`、`dateTo`、错误原因摘要、失败时间戳 }）并继续处理后续片；当 ≥1 片成功且 ≥1 片失败时，整体任务状态置为 `PARTIAL_SUCCESS`；当全部片失败时，整体任务状态置为 `FAILED`。
8. THE Data_Extraction_Module SHALL 在每次模板执行前后输出结构化日志，含字段 { 任务编号、参数代码、日期范围、命中行数、耗时（毫秒）}，日志级别默认 `INFO`。

### Requirement 5: 统一 API 响应包装与错误码

**User Story:** 作为前端开发者与排障人员，我需要所有 SpringBoot_Backend 接口遵循统一的响应包装与错误码规则，方便前端做统一拦截、方便日志按 `requestId` 串联。

#### Acceptance Criteria

1. THE SpringBoot_Backend SHALL 对所有 `/api/**` 接口返回 JSON，根对象包含字段 `success`（布尔）、`code`（整型，取值范围 [100, 9999]）、`message`（字符串，长度 0–500 字符）、`data`（对象 / 数组 / null）、`timestamp`（Long，UTC epoch 毫秒）、`requestId`（字符串，长度 26 字符 ULID 或 36 字符 UUID）。
2. WHEN 业务调用成功，THE SpringBoot_Backend SHALL 返回 `success = true`、`code = 200`、`message = ""`、`data` 为业务对象。
3. IF 调用方未携带有效 Token 且鉴权启用，THEN THE SpringBoot_Backend SHALL 返回 `success = false`、`code = 401`、`message`（非空字符串、长度 1–500 字符）、`data = null`。
4. IF 调用方已认证但缺少所需权限码，THEN THE SpringBoot_Backend SHALL 返回 `success = false`、`code = 403`、`message`（非空字符串、长度 1–500 字符）、`data = null`。
5. IF 后端业务异常（包括上游 Source_Database 不可用、SQL 执行失败），THEN THE SpringBoot_Backend SHALL 返回 `success = false`、`code = 500`、`message`（长度 1–500 字符且不含完整堆栈、SQL 原文、内部文件路径或主机名的错误类别简述）、`data = null`，且后端日志中记录完整堆栈与 `requestId`。
6. THE SpringBoot_Backend SHALL 为每个进入的 HTTP 请求生成 `requestId`（UUID 36 字符或 ULID 26 字符），同一进程运行期内不重复，并在响应包装与服务端日志中均输出该值。
7. THE SpringBoot_Backend SHALL 对涉及分页的查询接口返回结构 `{ records, total, size, current, pages }`（沿用 MyBatis-Plus 风格），分页请求参数命名为 `pageNo`（从 1 开始，取值范围 [1, 10000]）与 `pageSize`（默认 15，取值范围 [1, 200]）。
8. WHERE 请求路径不属于 `/api/**`，THE SpringBoot_Backend SHALL NOT 强制套用 API_Response_Wrapper（例如 actuator 健康检查接口保持原样）。
9. THE SpringBoot_Backend SHALL 仅在响应通过 HTTP 层成功发送给客户端后，才将该请求计入正常成功计数。
10. IF 响应在序列化或网络传输阶段失败，THEN THE SpringBoot_Backend SHALL 按 R9 中定义的运行期错误日志格式记录错误日志，且 SHALL NOT 把该请求计入正常成功计数。

### Requirement 6: 持久层与多数据源配置

**User Story:** 作为后端开发与部署人员，我需要 Persistence_Layer 基于 MyBatis、对接现有 SQL Server 数据库，且支持多数据源；数据库连接信息可由外部配置注入而非硬编码。

#### Acceptance Criteria

1. THE Persistence_Layer SHALL 在 MyBatis 与 MyBatis-Plus 中选择恰好 1 个作为唯一 ORM / SQL 映射框架，SHALL NOT 同时引入两者，SHALL NOT 引入其他 ORM（如 Hibernate / JPA / JOOQ）。
2. THE Persistence_Layer SHALL 通过 TCP 1433 端口对接 Source_Database（SQL Server），且初始数据库名取值 SHALL 与 `setting.ini` 中 `[DATABASE]` 段保持兼容（即 `labworks` 或 `labworks_wsduat` 之一，由 `application.yml` 指定）。
3. THE SpringBoot_Backend SHALL 把全部数据库连接参数（`host`、`port`、`database`、`username`、`password`）放在 `application.yml`（或 Spring Cloud Config / 环境变量）中，SHALL NOT 在 `.java` 源码、`.properties` 字面量或 Mapper XML 中以明文形式出现上述任一参数的实际取值。
4. THE Persistence_Layer SHALL 把原 `gencsv/sqltemplate/*.sql` 中的查询逻辑迁移为 MyBatis Mapper XML 或注解化 SQL，且 SHALL 通过 MyBatis 参数绑定（`#{}` 占位符）传入所有动态 SQL 参数（包括但不限于日期范围起止值、采样点编号、分类条件、分页参数），SHALL NOT 使用字符串拼接（含 `${}` 直接拼接用户输入）方式构造 WHERE / ORDER BY 等子句。
5. THE Persistence_Layer SHALL 通过 `application.yml` 显式声明 ≥2 个数据源条目（覆盖水质 / 黑点等不同业务库），并 SHALL 按 Mapper 包路径或 Mapper 上的数据源标识注解路由到对应数据源（同一 Mapper 在运行期路由到的数据源唯一确定）。
6. IF 在启动阶段（即从应用进程启动到 Spring ApplicationContext 完成 refresh 之间）任一已声明数据源的首次连接尝试在 `application.yml` 配置的连接超时时间（未配置时默认 30 秒）内未建立成功，THEN THE SpringBoot_Backend SHALL 在标准错误日志输出中至少记录以下字段：时间戳、`host`、`port`、`database`、异常类名、异常 message，且 SHALL NOT 输出 `password` 或包含 `password` 明文的连接字符串片段，并 SHALL 使 `/actuator/health` 在该次启动周期内持续返回 `DOWN`。
7. WHILE 应用处于启动阶段且尚未发起首次数据库连接尝试，THE SpringBoot_Backend SHALL 允许 `/actuator/health` 返回 `UP`（不强制必须 `DOWN`）。
8. WHERE 数据库连接错误发生在启动阶段之外（运行期重连失败），THE SpringBoot_Backend SHALL 通过 R9 中定义的运行期错误日志输出该事件，SHALL NOT 强制按本 Requirement 第 6 条的"启动阶段错误日志"格式重复输出。

### Requirement 7: 前后端分离 / 跨域 / 部署形态

**User Story:** 作为前端与运维，我需要 SpringBoot_Backend 以独立服务部署、与前端 Leaflet 应用解耦，且能正确处理跨域请求。

#### Acceptance Criteria

1. THE SpringBoot_Backend SHALL 通过 Spring Boot 内嵌容器（Tomcat 默认）独立启动，SHALL NOT 嵌入任何 HTML 模板渲染（不再使用 Jinja2 / Thymeleaf 服务端渲染地图页）。
2. THE SpringBoot_Backend SHALL 不提供等价于原 Flask 路由 `/maps/output/<view_type>/<filename>` 的静态 HTML 文件服务能力。
3. THE SpringBoot_Backend SHALL 对所有 `/api/**` 接口启用 CORS：允许的 HTTP 方法为 `GET` / `POST` / `OPTIONS`；允许的请求头至少包含 `Content-Type` / `Authorization` / `X-Request-Id`；默认不允许携带凭据（`allowCredentials = false`）；允许的 Origin 列表由 `application.yml` 中的 `app.cors.allowed-origins` 配置项注入。
4. IF 请求 Origin 不在 `app.cors.allowed-origins` 白名单内（包含配置项缺失或为空两种情况，此时视为"无任何 Origin 被允许"），THEN THE SpringBoot_Backend SHALL 返回 `code = 403` 且不写入任何 CORS 响应头。
5. THE SpringBoot_Backend SHALL 暴露 `/actuator/health` 健康检查端点，响应 `Content-Type` 为 `application/json`，首字节响应时间 ≤ 1 秒，负载内容仅含 `{ "status": "UP" | "DOWN" }`，SHALL NOT 在该端点输出数据库地址、版本号或其他内部信息。
6. THE SpringBoot_Backend SHALL 默认监听端口 `server.port = 5000`（可由配置项 `server.port` 覆盖）。

### Requirement 8: 鉴权与权限码（占位 / 默认禁用）

**User Story:** 作为安全与合规负责人，我需要明确新后端是否启用鉴权；如启用，则按全局接口规范中的 Token / 权限码约定接入。当前默认禁用以对齐内网无鉴权现状。

#### Acceptance Criteria

1. WHERE `app.security.enabled = false`（默认值，对齐现有 Flask 内网无鉴权状态），THE SpringBoot_Backend SHALL 允许所有 `/api/**` 请求免 Token 通过，且 SHALL 在启动日志中以 `WARN` 级别输出固定文本 `Security disabled: all API endpoints are public`，且 SHALL NOT 因为缺失 / 无效 Token 而返回 `code = 401`。
2. WHEN `app.security.enabled = true` 且请求头携带格式合法的 `Authorization: Bearer xxx`（其中 Token 字符串长度 1–4096 字符），THE SpringBoot_Backend SHALL 校验该 Token 并按业务流程继续处理。
3. IF `app.security.enabled = true` 且请求缺失 `Authorization` 头、或 Token 字符串为空、或 Token 校验失败（无效 / 过期），THEN THE SpringBoot_Backend SHALL 按 R5 中关于 401 的条款返回 `code = 401`。
4. WHERE 启用鉴权，THE SpringBoot_Backend SHALL 在 Controller 上以注解（如 `@RequiresPermissions("water-quality:measurement:query")`）声明权限码，权限码格式为 `{module}:{submodule}:{action}`，每段长度 1–32 字符、字符集限定为 `[a-z0-9-]`。
5. IF 启用鉴权且请求方已认证但缺少 Controller 上声明的权限码，THEN THE SpringBoot_Backend SHALL 按 R5 中关于 403 的条款返回 `code = 403`。
6. WHERE 启用鉴权，THE SpringBoot_Backend SHALL 通过统一请求拦截器对任意跨服务 HTTP 调用透传 `Authorization` 头，业务代码 SHALL NOT 显式拼装 Token。

### Requirement 9: 日志与可观测性

**User Story:** 作为运维与排障人员，我需要新后端的日志结构清晰、与原 `gencsv/log/` 日志能力对齐或更优，便于快速定位问题。

#### Acceptance Criteria

1. THE SpringBoot_Backend SHALL 使用 SLF4J + Logback（或等价框架），日志输出至控制台与相对路径 `./logs/` 目录；按自然日切割（00:00:00 触发新文件）；日志保留期 ≥ 30 天，超期文件 SHALL 自动归档或删除。
2. WHEN 任意 `/api/**` 请求被 Controller 处理，THE SpringBoot_Backend SHALL 输出包含字段 { 方法、路径、`requestId`、HTTP 状态码、耗时（毫秒）} 的访问日志；日志级别默认 `INFO`，HTTP 状态 5xx 时升级为 `ERROR`。
3. WHEN 任意水质 / 黑点查询接口耗时超过 `app.observability.slow-query-threshold-ms`（默认 3000 ms），THE SpringBoot_Backend SHALL 以 `WARN` 级别记录慢查询日志，含 { `requestId`、参数摘要、耗时（毫秒）}；参数摘要长度上限 500 字符，超出时截断并以 `...` 结尾。
4. THE SpringBoot_Backend SHALL NOT 在日志中输出敏感字段，敏感字段枚举为 { 数据库密码、Token / API Key、身份证号、手机号、邮箱 }；当日志格式化模板中出现上述字段时，SHALL 以 `***` 占位符替换。
5. IF 日志写入文件失败（如磁盘满、权限不足），THEN THE SpringBoot_Backend SHALL 通过 stderr 降级输出该日志，且 SHALL NOT 阻塞 API 请求处理。

## 接口路径汇总（按全局《接口设计规范》）

| 模块 | 路径 | 方法 | 用途 | 权限码（启用鉴权时） |
| --- | --- | --- | --- | --- |
| water-quality / measurement | `/api/water-quality/measurement/query` | POST | 水质测量数据查询（GeoJSON） | `water-quality:measurement:query` |
| water-quality / blackspot | `/api/water-quality/blackspot/query` | POST | 黑点数据查询（GeoJSON） | `water-quality:blackspot:query` |
| water-quality / parameter | `/api/water-quality/parameter/list` | GET | 参数元数据 + 色阶规则 | `water-quality:parameter:list` |
| water-quality / extraction | `/api/water-quality/extraction/archive` | POST | 触发批量归档（手动 HTTP） | `water-quality:extraction:archive` |
| water-quality / extraction | `/api/water-quality/extraction/archive/detail/{taskId}` | GET | 查询归档任务状态 | `water-quality:extraction:archive` |

---

**需求文档已根据用户拍板结果定稿，可进入设计阶段。**

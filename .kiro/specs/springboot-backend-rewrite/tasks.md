# Implementation Plan: springboot-backend-rewrite

## Overview

把现有 Python（Flask + folium + 独立 `gencsv` 脚本）后端整体重写为 **Java 17 + Spring Boot 3.x** 后端，只对外输出 GeoJSON / JSON 数据接口。实现采用设计文档已拍板的全部推荐决策（D1–D9）：

- **D1/D6** 持久层使用 **MyBatis-Plus** 作为唯一 ORM。
- **D2** 多数据源使用 baomidou `dynamic-datasource-spring-boot-starter` + `@DS` 注解路由。
- **D3** 归档产物以 CSV 落 `./archive/`，命名沿用 `{parameter}_{dateFrom}_{dateTo}_{timestamp}.csv`。
- **D4** 归档任务状态用进程内 `ConcurrentHashMap` 存储（MVP，进程重启后丢失）。
- **D5** 色阶统一为半开区间 `[min, max)` 表达；Insufficient 用青色与"过高"红色区分。
- **D7** 采样命中但 `district_gps.csv` 无映射的区：丢弃该区 Feature 并 `WARN` 记日志；对外 `value` 取 `result` 列。
- **D8** 基础包名 `com.watermap`，单模块结构。
- **D9** 鉴权使用 Spring Security + 自定义过滤器，默认禁用。

实现遵循"分析→实现→验证"原则，每个任务在前序任务基础上增量推进，最终串联为可启动服务。属性测试使用 **jqwik**（JUnit 5 平台），覆盖设计文档 Property 1–25，每条属性 `@Property(tries = 100)` 起步、以 `// Feature: springboot-backend-rewrite, Property {number}: {property_text}` 注释标注。

> 标注 `*` 的子任务为可选测试任务，可在 MVP 阶段跳过；核心实现任务不带 `*`，必须实现。

## Tasks

- [x] 1. 搭建项目骨架与构建配置
  - [x] 1.1 创建 Maven 项目骨架与 application.yml
    - 新建 `pom.xml`：Java 17、Spring Boot 3.x parent，引入 `spring-boot-starter-web`、`spring-boot-starter-actuator`、`spring-boot-starter-security`、`mybatis-plus-boot-starter`、`dynamic-datasource-spring-boot-starter`、`druid-spring-boot-starter`、`mssql-jdbc`、`net.jqwik:jqwik`（test scope）
    - 创建 `com.watermap.WaterMapApplication` 启动类与分层包目录（`config / common / metadata / measurement / blackspot / extraction / support`）
    - 编写 `application.yml`：`server.port=5000`、`spring.datasource.dynamic`（waterquality / blackspot 两数据源，连接参数全部用 `${ENV}` 占位）、`app.cors.allowed-origins=[]`、`app.security.enabled=false`、`app.observability.slow-query-threshold-ms=3000`、`app.extraction.archive-dir=./archive`
    - _Requirements: 6.3, 7.6, 8.1_

- [x] 2. 通用基础设施：响应包装、分页与 GeoJSON 模型
  - [x] 2.1 实现统一响应包装与错误码体系
    - 实现 `ApiResponse<T>`（`success/code/message/data/timestamp/requestId`）、`PageResult<T>`（`records/total/size/current/pages`）
    - 实现 `ErrorCode` 枚举（200/401/403/500/4001/4002/4003/4004/4005/归档 4xxx）与 `BusinessException`
    - _Requirements: 5.1, 5.2, 5.7_

  - [x]* 2.2 编写分页结构属性测试
    - **Property 22: 分页结构自洽**
    - **Validates: Requirements 5.7**
    - 验证 `pages == ceil(total / size)`，`pageSize∈[1,200]`、`pageNo∈[1,10000]`

  - [x] 2.3 实现 GeoJSON 输出模型与坐标精度序列化
    - 实现 `FeatureCollection` / `Feature` / `PointGeometry`（仅 `Point`），`coordinates` 顺序固定 `[longitude, latitude]`
    - 通过自定义 Jackson serializer 或构造前 `round(6)` 保证经纬度 6 位小数、测量值 2 位小数
    - _Requirements: 1.2, 2.2_

  - [x]* 2.4 编写 GeoJSON 几何不变量属性测试
    - **Property 1: GeoJSON 几何不变量**
    - **Validates: Requirements 1.2, 2.2**

- [x] 3. 色阶单一来源 ColorScaleRegistry
  - [x] 3.1 实现 ColorScaleRegistry（色阶定义 + 计算 + 拼接）
    - 定义 `ColorBand(level, color, min, max, description)`；按 D5 统一半开区间 `[min, max)`，`min` 含端点（null=−∞）、`max` 不含端点（null=+∞），按 `min` 升序（null 最前）
    - 录入 `cl2_free_1`(5 级)、`ecoli`(2 级)、`turby`(4 级) 色阶表（来自设计 4.5 节），连续覆盖 (−∞,+∞)
    - 实现 `resolveLevel(parameter, value)`：value 落入唯一区间返回 level；value 为 null/NaN 返回 null
    - 实现 `allParamsColorScale()`：按 `cl2_free_1`(5)+`ecoli`(2)+`turby`(4) 顺序同源拼接为 11 元素
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.9_

  - [x]* 3.2 编写色阶良构属性测试
    - **Property 10: 色阶有序且字段良构**
    - **Validates: Requirements 3.3**
    - 验证 `color` 匹配 `^#[0-9A-Fa-f]{6}$`、按 `min` 非降序、字段齐全

  - [x]* 3.3 编写色阶连续覆盖唯一命中属性测试
    - **Property 11: 色阶连续覆盖且唯一命中**
    - **Validates: Requirements 3.4, 3.5, 3.6**

  - [x]* 3.4 编写 all_params 同源拼接属性测试
    - **Property 12: all_params 色阶同源拼接**
    - **Validates: Requirements 3.7**

- [x] 4. 参数元数据接口
  - [x] 4.1 实现 ParameterMetadataService 与 Controller
    - 实现 `GET /api/water-quality/parameter/list`（无 query/path/body），复用 `ColorScaleRegistry` 输出 4 条目（`cl2_free_1/ecoli/turby/all_params`），含 `parameter/displayName/unit/colorScale`
    - _Requirements: 3.1, 3.2_

  - [x]* 4.2 编写元数据接口单元测试
    - 验证返回 ≥4 条目、字段齐全、`all_params` 含 11 元素、接口不接受任何参数
    - _Requirements: 3.1, 3.2_

- [x] 5. Checkpoint - 确保通用层与元数据测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 日期校验与坐标过滤通用逻辑
  - [x] 6.1 实现日期校验工具
    - 实现 `DateRangeValidator`：`YYYY-MM-DD` 格式校验、`dateFrom <= dateTo`（否则 4003 并指出第一个失败字段）、跨度上限校验（测量 90 天/4004、黑点 366 天/4004）
    - _Requirements: 1.8, 1.9, 2.3, 2.4_

  - [x]* 6.2 编写日期范围校验属性测试
    - **Property 5: 统一日期范围校验**
    - **Validates: Requirements 1.8, 2.3**

  - [x]* 6.3 编写日期跨度上限属性测试
    - **Property 6: 日期跨度上限校验**
    - **Validates: Requirements 1.9, 2.4**

  - [x] 6.4 实现坐标校验剔除与 meta 构建
    - 实现 `CoordinateFilter`：剔除 `lat/lon` 为空/非数值/越界（`lat∉[-90,90]` 或 `lon∉[-180,180]`）记录并累计 `droppedInvalidCoordinateCount`
    - 实现 `FeatureCollectionMeta` 构建（`featureCount` 等于 features 长度、各计数非负整数、`queryDurationMs`）
    - _Requirements: 1.10, 1.12, 2.5, 2.7_

  - [x]* 6.5 编写无效坐标剔除计数守恒属性测试
    - **Property 7: 无效坐标剔除与计数守恒**
    - **Validates: Requirements 1.10, 2.5**

  - [x]* 6.6 编写 meta 计数一致性属性测试
    - **Property 8: meta 计数一致性**
    - **Validates: Requirements 1.12, 2.7**

- [x] 7. 持久层与多数据源
  - [x] 7.1 配置 MyBatis-Plus 与多数据源
    - 配置 `dynamic-datasource` + Druid 连接池 + `mssql-jdbc` 驱动；声明 `waterquality` / `blackspot` 两数据源（TCP 1433），连接超时默认 30s
    - 配置 MyBatis-Plus 分页插件；Mapper 按包路径或 `@DS` 注解路由（运行期唯一确定）
    - _Requirements: 6.1, 6.2, 6.5_

  - [x] 7.2 迁移水质 SQL 模板为 MyBatis Mapper
    - 把 `gencsv/sqltemplate/{cl2_free_1,ecoli,turby}.sql` 迁移为 Mapper XML，`[date_from]`/`[date_to]` 改为 `#{dateFrom}`/`#{dateTo}` 命名参数绑定，去除 `TOP 1000` 硬限制，`acode` 由各 Mapper 固定
    - 定义 `MeasurementRow`（`sampleNo/locationCode/locationDesc/currentState/collectedAt/district/latitude/longitude/value(result)/rawResult`）
    - _Requirements: 4.2, 6.4_

- [x] 8. District 中心点加载
  - [x] 8.1 实现 DistrictGpsRepository
    - 启动加载 `gencsv/missing_gps/district_gps.csv`，提供 `district(小写) → (lat,lon)` 查询；同一 district 多行取首行（D7）
    - 采样命中但无 GPS 映射的区：丢弃该区 Feature 并以 `WARN` 记日志
    - _Requirements: 1.3, 1.5_

- [x] 9. 水质测量查询
  - [x] 9.1 实现 MeasurementService 聚合逻辑
    - 实现三种视图：`district`（按区聚合，输出 `avgValue/maxValue/minValue/sampleCount/colorLevel`，坐标取 District_GPS）、`detailed`（逐点，输出全字段含 `collectedAt` 为 +08:00）、`district_all_param`（每区一 Feature，各 Parameter_Code 子对象含 `avgValue/colorLevel`）
    - `colorLevel` 一律调用 `ColorScaleRegistry.resolveLevel`；剔除无效坐标后有效 Feature > 50000 抛 4005
    - _Requirements: 1.3, 1.4, 1.5, 1.13, 3.8, 3.9_

  - [x]* 9.2 编写 district 聚合属性测试
    - **Property 2: district 聚合不变量**
    - **Validates: Requirements 1.3**

  - [x]* 9.3 编写 detailed 逐点映射属性测试
    - **Property 3: detailed 逐点映射不变量**
    - **Validates: Requirements 1.4**

  - [x]* 9.4 编写 district_all_param 多参数结构属性测试
    - **Property 4: district_all_param 多参数结构不变量**
    - **Validates: Requirements 1.5**

  - [x]* 9.5 编写结果集上限熔断属性测试
    - **Property 9: 结果集上限熔断**
    - **Validates: Requirements 1.13**

  - [x]* 9.6 编写 colorLevel 同源一致属性测试
    - **Property 13: colorLevel 与色阶同源一致**
    - **Validates: Requirements 3.8**

  - [x]* 9.7 编写无效测量值 colorLevel 置空属性测试
    - **Property 14: 无效测量值的 colorLevel 置空且保留 Feature**
    - **Validates: Requirements 3.9**

  - [x] 9.8 实现 MeasurementController 与组合校验
    - 实现 `POST /api/water-quality/measurement/query`；按短路顺序校验：必填/枚举 → 组合(`all_params` 仅 `district_all_param`/4001；`{cl2_free_1,ecoli,turby}` 不允许 `district_all_param`/4002) → 日期(4003) → 跨度(4004) → 查询 → 结果集(4005)
    - 命中为零返回 `code=200` 且 `features=[]`
    - _Requirements: 1.1, 1.6, 1.7, 1.11_

  - [x]* 9.9 编写参数×视图组合校验单元测试
    - 验证 4001/4002 错误码与 message、命中为零行为
    - _Requirements: 1.6, 1.7, 1.11_

- [x] 10. Checkpoint - 确保测量查询与持久层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 黑点查询
  - [x] 11.1 实现 BlackspotMapper / Service / Controller
    - 按 `bp_data.csv` 字段（`case_id/lat/lon/location_desc/report_date`）定义 `BlackspotRow` 与 Mapper（路由 `blackspot` 数据源，`#{}` 参数绑定）
    - 实现 `POST /api/water-quality/blackspot/query`：复用日期校验(366 天)、坐标剔除与 meta 构建；输出 Feature 含 `caseId/locationDesc/reportDate`
    - _Requirements: 2.1, 2.2, 2.4, 2.6, 2.7_

  - [x]* 11.2 编写黑点查询属性测试（复用几何/剔除/meta 不变量）
    - **Property 1 / Property 7 / Property 8**（黑点接口侧验证）
    - **Validates: Requirements 2.2, 2.5, 2.7**

- [x] 12. 数据采集归档模块
  - [x] 12.1 实现 DateRangeSlicer
    - 按 `rangeDays`/`stepDays` 生成日期窗口（沿用 `date_range_runner.generate_date_ranges` 回看窗口语义），连续覆盖请求区间
    - _Requirements: 4.5_

  - [x]* 12.2 编写日期切片覆盖属性测试
    - **Property 17: 日期切片覆盖与窗口规整**
    - **Validates: Requirements 4.5**

  - [x] 12.3 实现 ArchiveTaskStore 与整体状态判定
    - 进程内 `ConcurrentHashMap` 存储 `ArchiveTask`（D4）；按片成功/失败计数判定整体状态：`f>0∧s>0→PARTIAL_SUCCESS`、`f>0∧s=0→FAILED`、`f=0∧s>0→SUCCESS`
    - _Requirements: 4.6, 4.7_

  - [x]* 12.4 编写归档整体状态判定属性测试
    - **Property 18: 归档整体状态判定**
    - **Validates: Requirements 4.7**

  - [x] 12.5 实现 CSV 归档写入器
    - 每片结果落 `./archive/`，文件名 `{parameter}_{dateFrom}_{dateTo}_{timestamp}.csv`，`timestamp` 格式 `yyyyMMdd_HHmmss`
    - _Requirements: 4.5_

  - [x]* 12.6 编写归档产物命名属性测试
    - **Property 16: 归档产物命名约定**
    - **Validates: Requirements 4.5**

  - [x] 12.7 实现 ExtractionController 与异步归档 Service
    - 实现 `POST /api/water-quality/extraction/archive`：同步校验（缺失/越界 [1,365]/格式/`from>to` → 4xxx 且不启动任务），同步返回 `taskId`（≤5s），`@Async` 异步执行逐片查询；单片失败记录 `ArchiveError` 并继续
    - 每片执行前后输出结构化 `INFO` 日志（任务编号/参数代码/日期范围/命中行数/耗时）
    - _Requirements: 4.1, 4.3, 4.4, 4.8_

  - [x]* 12.8 编写归档参数非法拒绝属性测试
    - **Property 15: 归档参数非法即拒绝且不启动任务**
    - **Validates: Requirements 4.4**

  - [x] 12.9 实现归档任务详情查询接口
    - 实现 `GET /api/water-quality/extraction/archive/detail/{taskId}`：返回状态/成功片数/失败片数/产物清单/错误清单
    - _Requirements: 4.6_

- [x] 13. Checkpoint - 确保黑点与归档测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. 横切 Web 组件
  - [x] 14.1 实现 RequestIdFilter
    - 为每请求生成 UUID(36)/ULID(26)，写入 MDC 与响应头 `X-Request-Id`，进程内不重复
    - _Requirements: 5.6_

  - [x]* 14.2 编写 requestId 唯一格式属性测试
    - **Property 21: requestId 唯一且格式合法**
    - **Validates: Requirements 5.6**

  - [x] 14.3 实现 ApiResponseBodyAdvice
    - 对 `/api/**` 自动包装为 `ApiResponse`；放行 `/actuator/**` 等非 `/api/**` 路径；仅响应成功发送后计成功
    - _Requirements: 5.1, 5.2, 5.8, 5.9, 5.10_

  - [x]* 14.4 编写统一响应包装良构属性测试
    - **Property 19: 统一响应包装良构**
    - **Validates: Requirements 5.1, 5.2**

  - [x] 14.5 实现 GlobalExceptionHandler 与 SensitiveMessageSanitizer
    - `@RestControllerAdvice` 集中处理业务/校验/系统异常映射错误码；对外 message 经 `SensitiveMessageSanitizer` 过滤堆栈/SQL/路径/主机名，`code=500`，日志记录完整堆栈 + requestId
    - _Requirements: 5.3, 5.4, 5.5_

  - [x]* 14.6 编写错误 message 脱敏属性测试
    - **Property 20: 错误 message 脱敏**
    - **Validates: Requirements 5.5**

  - [x] 14.7 实现 AccessLogInterceptor
    - 出口访问日志（方法/路径/requestId/状态码/耗时），5xx 升 `ERROR`；慢查询（默认 >3000ms）`WARN`，参数摘要 >500 字符截断并以 `...` 结尾
    - _Requirements: 9.2, 9.3_

  - [x]* 14.8 编写慢查询摘要截断属性测试
    - **Property 24: 慢查询参数摘要截断**
    - **Validates: Requirements 9.3**

- [x] 15. CORS / 安全 / 日志 / 健康检查
  - [x] 15.1 实现 CorsConfig
    - 对 `/api/**` 配置 CORS：方法 GET/POST/OPTIONS；头 Content-Type/Authorization/X-Request-Id；`allowCredentials=false`；Origin 取自 `app.cors.allowed-origins`；白名单缺失/为空时不放行任何 Origin、返回 403 且不写任何 CORS 头
    - _Requirements: 7.3, 7.4_

  - [x]* 15.2 编写非白名单 Origin 拒绝属性测试
    - **Property 23: 非白名单 Origin 一律拒绝**
    - **Validates: Requirements 7.4**

  - [x] 15.3 实现 SecurityConfig 与 TokenAuthFilter
    - `app.security.enabled=false`（默认）放行全部 `/api/**` 并在启动日志 `WARN` 输出固定文本 `Security disabled: all API endpoints are public`，不因缺/无效 Token 返回 401
    - `=true` 时校验 `Authorization: Bearer`（长度 1–4096），失败 401；权限码注解 `{module}:{submodule}:{action}` 缺失 403；拦截器透传 `Authorization`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x]* 15.4 编写安全禁用/启用单元测试
    - 验证默认禁用放行 + WARN 文本、启用后 401/403 行为
    - _Requirements: 8.1, 8.3_

  - [x] 15.5 配置 Logback 与脱敏
    - 控制台 + `./logs/` 按自然日切割、保留 ≥30 天；`MaskingPatternLayout` 把密码/Token/API Key/身份证/手机/邮箱替换为 `***`；写文件失败降级 stderr 不阻塞请求
    - _Requirements: 9.1, 9.4, 9.5_

  - [x]* 15.6 编写敏感字段脱敏属性测试
    - **Property 25: 敏感字段脱敏**
    - **Validates: Requirements 9.4**

  - [x] 15.7 配置 actuator/health 与端口、禁用旧静态路由
    - `/actuator/health` 返回 `application/json` 仅含 `{status}`、不输出内部信息；默认端口 5000；启动期数据源连接失败记脱敏日志并使 health 持续 DOWN；不提供 `/maps/output/*` 静态 HTML（返回 404）
    - _Requirements: 6.6, 6.7, 7.1, 7.2, 7.5_

- [x] 16. 集成装配与最终校验
  - [x] 16.1 串联启动类与过滤器/拦截器链路
    - 装配 RequestIdFilter → CorsFilter →（可选）TokenAuthFilter → AccessLogInterceptor → Controller → ResponseBodyAdvice 链路，确保无孤立组件，应用可启动
    - _Requirements: 5.1, 7.1, 7.3_

  - [x]* 16.2 编写集成冒烟测试
    - 验证应用启动、`/actuator/health`、旧 `/maps/output/*` 返回 404、多数据源装配与路由唯一、连接参数无明文（grep）、默认端口 5000
    - _Requirements: 6.2, 6.5, 7.2, 7.5, 7.6_

- [x] 17. 最终 Checkpoint - 确保全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标注 `*` 的子任务为可选测试任务，可为加速 MVP 跳过；核心实现任务不带 `*`，必须实现。
- 每个任务标注其对应的需求条目（granular 子需求），保证可追溯。
- Checkpoint 任务用于增量验证，确保前序任务测试全部通过后再推进。
- 属性测试（jqwik）验证 Property 1–25 的全称不变量；DB 相关逻辑用 mock / 内存夹具隔离，避免对真实 SQL Server 的高成本调用；50000 上限（Property 9）用桩数据模拟跨阈。
- 单元 / 例子测试验证具体场景与边界（组合校验、命中为零、安全禁用 WARN、actuator 不套包装、旧路由 404 等）。
- D6 黑点真实业务库表名与 SQL 尚未提供，任务 11.1 先按 `bp_data.csv` 字段结构落地 Mapper，真实库 SQL 需在实现前确认。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.3", "3.1", "6.1", "6.4", "7.1", "8.1", "12.1", "12.3", "14.1", "15.1", "15.3", "15.5"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.2", "3.3", "3.4", "4.1", "6.2", "6.3", "6.5", "6.6", "7.2", "12.2", "12.4", "12.5", "14.2", "14.3", "14.5", "14.7", "15.2", "15.4", "15.6", "15.7"] },
    { "id": 3, "tasks": ["4.2", "9.1", "11.1", "12.6", "12.7", "14.4", "14.6", "14.8"] },
    { "id": 4, "tasks": ["9.2", "9.3", "9.4", "9.5", "9.6", "9.7", "9.8", "11.2", "12.8", "12.9"] },
    { "id": 5, "tasks": ["9.9", "16.1"] },
    { "id": 6, "tasks": ["16.2"] }
  ]
}
```

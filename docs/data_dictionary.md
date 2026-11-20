# 数据字典

## 1. 数据来源与版本

本仓库面向 KuaiRand-27K，原始数据由 [KuaiRand 官方仓库](https://github.com/chongminggao/KuaiRand) 发布。数据使用受原始发布方许可约束，仓库 MIT License 不覆盖第三方数据。

完整 CSV 的字段数、行数、键唯一性、非法值、时间范围和关联覆盖由 `sql/01_quality.sql` 在运行时计算，具体检查结果见[最终报告](../reports/final_report.md)的数据质量部分。

## 2. 原始文件与粒度

| 文件角色 | 文件数 | 官方字段数 | 原始粒度 |
|---|---:|---:|---|
| `log_random_*.csv` | 1 | 19 | 一次随机干预曝光/交互事件 |
| `log_standard_*.csv` | 4 | 19 | 一次标准推荐曝光/交互事件 |
| `user_features_27k.csv` | 1 | 31 | 一行一户 |
| `video_features_basic_27k.csv` | 1 | 12 | 一行一视频的基础属性 |
| `video_features_statistic_27k_part*.csv` | 3 | 52 | 一行一视频的月内按日、按场景汇总 |

标准日志分片可以包含同一 `user_id` 和 `video_id` 的多次接触。`(user_id, video_id)` 不是事件唯一键；分析不以该组合简单去重。

## 3. 日志字段

| 字段 | 标准化类型 | 含义与处理 |
|---|---|---|
| `user_id` | `BIGINT` | 匿名用户 ID；为空的事件不进入业务 Marts |
| `video_id` | `BIGINT` | 匿名视频 ID；为空的事件不进入业务 Marts |
| `date` | `DATE` | 由原始 `YYYYMMDD` 整数解析为日历日期 |
| `hourmin` | `INTEGER` | 原表的粗粒度时段字段；本仓库用 `date + hourmin` 定义事件日与小时 |
| `time_ms` | `BIGINT` | Unix 毫秒时间戳；用于构造本地时间与排序 |
| `is_click` | `INTEGER` | 二元反馈；双列 UI 中表示点击，单列 UI 中表示有效播放。有效播放的发布方阈值为：`duration_ms <= 7000` 时 `play_time_ms >= duration_ms`，否则 `play_time_ms > 7000`。点击率只在同类 UI 场景内比较 |
| `is_like` | `INTEGER` | 本曝光事件是否带点赞标记 |
| `is_follow` | `INTEGER` | 本曝光事件是否带关注作者标记 |
| `is_comment` | `INTEGER` | 本曝光事件是否带评论标记 |
| `is_forward` | `INTEGER` | 本曝光事件是否带转发标记 |
| `is_hate` | `INTEGER` | 本曝光事件是否带不喜欢标记 |
| `long_view` | `INTEGER` | 发布方长观看标记：`duration_ms <= 18000` 时 `play_time_ms >= duration_ms`，否则 `play_time_ms >= 18000` |
| `play_time_ms` | `BIGINT` | 原始观看时长，毫秒；0 表示该事件未获得有效观看时长 |
| `duration_ms` | `BIGINT` | 原始视频时长，毫秒；0 保留为曝光事件，但不计算观看深度 |
| `profile_stay_time` | `BIGINT` | 作者主页停留时间，毫秒 |
| `comment_stay_time` | `BIGINT` | 评论区域停留时间，毫秒 |
| `is_profile_enter` | `INTEGER` | 是否进入作者主页 |
| `is_rand` | `INTEGER` | 随机干预标记；标准来源应为 0，随机来源应为 1 |
| `tab` | `INTEGER` | 场景编号，官方范围为 0 至 14；本仓库不赋予未核实的场景名称 |

`play_time_ms > duration_ms` 保留原值，不作为非法记录删除。现有字段不能区分重复播放、循环播放或计量差异，因此本仓库不据此认定记录真假。负数观看时长、非法二元值、非法场景编号、无效 ID 或无效时间会阻止事件进入 Marts。

## 4. 用户特征

| 字段组 | 类型 | 说明 |
|---|---|---|
| `user_id` | `BIGINT` | 用户主键候选 |
| `user_active_degree` | `VARCHAR` | 发布方给出的活跃程度分类 |
| `is_lowactive_period` | `INTEGER` | 是否处于发布方定义的低活跃期 |
| `is_live_streamer`, `is_video_author` | `INTEGER` | 是否主播、是否视频作者 |
| `follow_user_num`, `fans_user_num`, `friend_user_num` | `BIGINT` | 关注、粉丝、好友数量 |
| 对应 `*_range` | `VARCHAR` | 相应数量的分桶范围 |
| `register_days`, `register_days_range` | `BIGINT`, `VARCHAR` | 注册天数及分桶 |
| `onehot_feat0` 至 `onehot_feat17` | `DOUBLE` | 发布方加密特征；业务含义未公开 |

用户特征用于连接覆盖和描述性扩展现状，不作为回访模型的默认解释变量，避免不清楚的特征时间窗引入泄漏。加密 one-hot 特征不解释为人口属性。

## 5. 视频基础特征

| 字段 | 标准化字段/类型 | 说明 |
|---|---|---|
| `video_id` | `video_id`, `BIGINT` | 视频主键候选 |
| `author_id` | `author_id`, `BIGINT` | 匿名作者 ID |
| `video_type` | `video_type`, `VARCHAR` | 发布方类型，例如 `NORMAL`、`AD` |
| `upload_dt` | `upload_date`, `DATE` | 上传日期 |
| `upload_type` | `upload_type`, `VARCHAR` | 上传方式 |
| `visible_status` | `visible_status`, `DOUBLE` | 当前可见状态 |
| `video_duration` | `video_duration_ms`, `DOUBLE` | 视频时长，毫秒 |
| `server_width`, `server_height` | `DOUBLE` | 服务端视频尺寸 |
| `music_id`, `music_type` | `BIGINT`, `DOUBLE` | 背景音乐 ID 和类型编号 |
| `tag` | `tag`, `VARCHAR` | 逗号分隔的数值标签串；一个视频可对应多个标签 |

标签按逗号展开后仍使用原始数值 ID，不推断标签业务含义。

## 6. 视频统计特征

该表包含 `video_id`、`counts` 和 50 个数值统计字段。按发布方说明：

- 统计字段是一个月内按日、按场景平均后的汇总。
- `counts` 是该视频在统计期内形成记录的次数，不是标准日志事件数。
- `show_cnt`、`play_cnt`、`like_cnt` 等与逐条日志的曝光/反馈计数不是同一 grain。
- 因此本报告只用该表核对视频规模和汇总粒度，不把月度统计值连接到历史用户日模型。

## 7. 派生事件字段

| 派生字段 | 定义 | 用途 |
|---|---|---|
| `source_type` | `standard` 或 `random` | 强制区分来源 |
| `source_file` | 原始文件名 | 溯源 |
| `event_date` | 原始 `date` 解析后的日期 | 日历日聚合 |
| `event_ts_local` | `epoch_ms(time_ms)` 加 UTC+8 偏移 | 时间戳溯源和质量比较 |
| `source_hour` | `floor(hourmin / 100)` | 粗粒度小时保留 |
| `watch_depth_ratio` | `play_time_ms / duration_ms`，分母为 0 时为空 | 观看深度 |
| `is_date_time_consistent` | 原始日期是否等于时间戳的 UTC+8 日期 | 全量质量检查 |
| `is_valid_event` | ID、日期、时间、`hourmin`、二元值、场景、时长与来源标记的联合校验 | 业务 Marts 过滤 |

## 8. 业务 Marts

| 表 | 粒度 | 关键键/说明 |
|---|---|---|
| `mart_user_day` | 用户日 | `(user_id, activity_date)` 唯一；只含有效标准日志 |
| `mart_user_summary` | 用户 | 首次/末次观测日期、活跃天数、总事件、互动计数和活跃分位组 |
| `mart_daily_activity` | 日期 | DAU、事件数、事件/DAU、标记率、首次观测用户数 |
| `mart_hourly_activity` | 日期和本地小时 | 小时活跃用户和事件 |
| `mart_cohort_return` | 用户、首次观测日和 offset | 是否合格、精确目标日是否回访 |
| `mart_return_model` | 用户日 | `t` 日参与特征及 `t+1`、`t+7`、第 1 至 7 日结局 |
| `mart_video_performance` | 视频 | 标准日志事件汇总；不是视频质量真值 |
| `mart_content_*` | 视频类型/时长段/标签 | 曝光加权与视频等权口径分开 |

连接规则：

- 用户特征连接键为 `user_id`。
- 视频基础/统计特征连接键为 `video_id`。
- 日志事件按 `source_type`、`source_file` 和 `time_ms` 保留来源与时序。
- 跨表连接覆盖率单独验证，不预设 100% 匹配。

## 9. 日期的口径

全量检查中，2,359,097 条记录的原始 `date` 比 `time_ms` 转换后的 UTC+8 日期晚一天，集中出现在时间戳的 21 至 23 时。这些记录的 `date` 与 `hourmin` 构成一致的源端交互日/小时。为保证 DAU、Cohort 和时段口径与发布方的交互字段一致，本仓库以 `date` 定义 `event_date`、以 `hourmin` 定义小时，保留 `time_ms` 用于溯源、排序和差异诊断。

项目同时执行了日期口径敏感性：源端日期下精确 D7 为 93.24%，UTC+8 时间戳日期下为 93.11%，全样本主要结论一致；排除首日后的 D7 分别为 74.15% 和 92.71%，说明该边界口径依赖日期定义。具体对账见[最终报告](../reports/final_report.md)第 2.3 节和[方法说明](methodology.md)第 12 节。

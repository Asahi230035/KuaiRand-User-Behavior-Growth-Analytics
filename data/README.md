# KuaiRand-27K 数据文件说明

本仓库不分发原始数据及其派生数据。请依据 [KuaiRand 官方仓库](https://github.com/chongminggao/KuaiRand) 的获取方式、授权和使用说明，在本地保存 KuaiRand-27K 的 10 个 CSV 文件。数据受原始发布方许可管理，本仓库的 MIT License 不覆盖第三方数据。

默认位置为 `data/raw/`；也可以通过 `config.yaml` 或命令行 `--raw-dir` 指定仓库外的原始数据目录，避免重复占用磁盘空间。原始 CSV 不应被修改或提交至 Git。

## 预期文件

```text
log_random_4_22_to_5_08_27k.csv
log_standard_4_08_to_4_21_27k_part1.csv
log_standard_4_08_to_4_21_27k_part2.csv
log_standard_4_22_to_5_08_27k_part1.csv
log_standard_4_22_to_5_08_27k_part2.csv
user_features_27k.csv
video_features_basic_27k.csv
video_features_statistic_27k_part1.csv
video_features_statistic_27k_part2.csv
video_features_statistic_27k_part3.csv
```

数据处理产物可保存在本地 `data/processed/`、`data/marts/` 和 `data/results/`；它们属于可重新构建的计算结果，不属于公开仓库的版本管理内容。

完整数据包含四份标准推荐日志、一份随机干预日志、三份视频统计特征、一份用户特征和一份视频基础特征，共约 46 GiB。运行前至少预留 12 GiB 新输出空间；实际需求取决于配置和直接写入的文件系统。

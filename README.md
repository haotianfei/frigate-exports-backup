# Frigate 导出备份工具

该工具用于自动导出 Frigate NVR 系统的录像文件，并将其备份到指定位置。

## 功能

1. 自动导出指定日期和时间范围的 Frigate 录像
2. 支持按固定间隔分段导出（如每4小时一个文件）
3. 监控导出进度并等待导出完成，显示任务名称、摄像头、文件大小和已执行时间
4. 将导出的文件移动到目标备份目录
5. 清理过期的备份文件
6. 清理 Frigate 中的原始导出记录

## 配置

工具需要配置文件才能运行，不再在代码中包含默认配置。

### 配置文件

创建 `config.ini` 文件来自定义配置：

```ini
[frigate]
# Frigate API URL
api_url = http://YOUR_FRIGATE_IP:PORT

# 源路径 - Frigate导出文件所在目录
source_path = /path/to/frigate/exports

# 目标路径 - 备份文件存储目录
dest_path = /path/to/backup/storage

# 导出文件保留天数
export_retention_days = 30

# 导出多少天前的录像，例如设置为5表示导出5天前的录像
export_days_ago = 5

# 时区设置
timezone = Asia/Shanghai
```

也可以复制 `config.example.ini` 作为模板：

```bash
cp config.example.ini config.ini
```

然后修改 `config.ini` 中的配置项以匹配你的环境。

配置项说明：
- `api_url`: Frigate的API地址
- `source_path`: Frigate导出文件所在的目录
- `dest_path`: 备份文件存储的目标目录
- `export_retention_days`: 导出文件保留天数，超过此天数的文件会被自动清理
- `export_days_ago`: 导出多少天前的录像（可选，默认为1，即导出昨天的录像）
- `timezone`: 时区设置（可选，默认为Asia/Shanghai）

### 命令行参数

```
usage: frigate-exporter.py [-h] [--cameras CAMERA [CAMERA ...]]
                           [--date DATE] [--start-hour START_HOUR]
                           [--end-hour END_HOUR] [--split-interval SPLIT_INTERVAL]
                           [--config CONFIG]

Frigate录像导出和备份工具

optional arguments:
  -h, --help            show this help message and exit
  --cameras CAMERA [CAMERA ...], -c CAMERA [CAMERA ...]
                        指定要导出的摄像头列表（默认导出所有摄像头）
  --date DATE           指定导出日期，格式为 YYYY-MM-DD（默认为配置文件中指定的天数前）
  --start-hour START_HOUR
                        导出开始时间（小时，0-24，默认为0），0表示00:00:00
  --end-hour END_HOUR   导出结束时间（小时，0-24，默认为24），24表示明日00:00:00（当天结束）
  --split-interval SPLIT_INTERVAL
                        按指定小时分割录像（不能与--start-hour/--end-hour同时使用）
  --config CONFIG       指定配置文件路径
```

## 新增功能说明

### 时间精确控制

- `--start-hour` 和 `--end-hour` 参数现在支持 0-24 的范围
- 默认情况下，不指定起止时间则导出 00:00:00 到 23:59:59 的录像
- 要导出完整的24小时录像，请使用 `--end-hour 24`

### 分段导出功能

通过 `--split-interval` 参数可以将一天分成多个时间段导出，每个时间段独立生成一个文件：

- `--split-interval 4`：每4小时一个文件（共6个文件：0-4, 4-8, 8-12, 12-16, 16-20, 20-24）
- `--split-interval 2`：每2小时一个文件（共12个文件：0-2, 2-4, 4-6, ..., 22-24）

**注意**：
- 分段导出的时间区间为左闭右开，例如 `[0,4)` 表示从00:00:00开始，到04:00:00结束（不含04:00:00）
- 不能同时使用 `--split-interval` 和 `--start-hour`/`--end-hour` 参数

## 使用示例

```
# 使用默认配置导出全天录像
python3 frigate-exporter.py --config config.ini -c camera_name

# 导出完整24小时录像（00:00:00-24:00:00）
python3 frigate-exporter.py --config config.ini -c camera_name --end-hour 24

# 导出指定时间段（00:00:00-04:00:00）
python3 frigate-exporter.py --config config.ini -c camera_name --start-hour 0 --end-hour 4

# 每4小时分割导出（推荐，减少单次磁盘占用）
python3 frigate-exporter.py --config config.ini -c camera_name --split-interval 4

# 每2小时分割导出
python3 frigate-exporter.py --config config.ini -c camera_name --split-interval 2
```

## 定时任务

推荐使用 cron 定时执行此脚本以实现自动化备份：

```
# 每天凌晨4点执行4小时间隔导出
00 04 * * * cd /srv/htf_data/docker/appdata/frigate/frigate-exports-backup && sudo /home/z240/.pyenv/shims/python3 frigate-exporter.py --config config.ini -c tplink_ipc44aw --split-interval 4
```

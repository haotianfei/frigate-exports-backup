# Frigate 导出备份工具

该工具用于自动导出 Frigate NVR 系统的录像文件，并将其备份到指定位置。

## 功能

1. 自动导出指定日期和时间范围的 Frigate 录像
2. 监控导出进度并等待导出完成
3. 将导出的文件移动到目标备份目录
4. 清理过期的备份文件
5. 清理 Frigate 中的原始导出记录

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
                           [--end-hour END_HOUR] [--config CONFIG]

Frigate录像导出和备份工具

optional arguments:
  -h, --help            show this help message and exit
  --cameras CAMERA [CAMERA ...], -c CAMERA [CAMERA ...]
                        指定要导出的摄像头列表（默认导出所有摄像头）
  --date DATE           指定导出日期，格式为 YYYY-MM-DD（默认为配置文件中指定的天数前）
  --start-hour START_HOUR
                        导出开始时间（小时，0-23，默认为0）
  --end-hour END_HOUR   导出结束时间（小时，0-23，默认为23）
  --config CONFIG       指定配置文件路径
```

## 使用示例

```bash
# 使用默认配置文件 (config.ini)
python3 frigate-exporter.py

# 指定配置文件
python3 frigate-exporter.py --config /path/to/custom-config.ini

# 指定日期和时间范围
python3 frigate-exporter.py --date 2025-11-15 --start-hour 9 --end-hour 17

# 指定摄像头
python3 frigate-exporter.py --cameras camera1 camera2
```

## 定时任务

推荐使用 cron 定时执行此脚本以实现自动化备份：

```bash
# 每天凌晨2点执行
0 2 * * * cd /path/to/frigate-exports-backup && python3 frigate-exporter.py
```
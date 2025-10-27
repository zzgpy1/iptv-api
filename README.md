<div align="center">
  <img src="./static/images/logo.png" alt="logo"/>
  <h1 align="center">IPTV-API</h1>
</div>

📺IPTV直播源自动更新平台，『✨全自动化采集、筛选、测速流程🚀』，支持丰富的个性化配置，生成结果输入播放器即可观看

<p align="center">
  <br>
  <a href="https://trendshift.io/repositories/12327" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12327" alt="Guovin%2Fiptv-api | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</p>

<p align="center">
  <a href="https://github.com/Guovin/iptv-api/releases/latest">
    <img src="https://img.shields.io/github/v/release/guovin/iptv-api" />
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-%20%3D%203.13-47c219" />
  </a>
  <a href="https://github.com/Guovin/iptv-api/releases/latest">
    <img src="https://img.shields.io/github/downloads/guovin/iptv-api/total" />
  </a>
  <a href="https://hub.docker.com/repository/docker/guovern/iptv-api">
    <img src="https://img.shields.io/docker/pulls/guovern/iptv-api" />
  </a>
  <a href="https://github.com/Guovin/iptv-api/fork">
    <img src="https://img.shields.io/github/forks/guovin/iptv-api" />
  </a>
</p>

<div align="center">

[English](./README_en.md) | 中文

</div>

🎉💻 [IPTV-Web](https://github.com/Guovin/iptv-web)：IPTV电视直播源管理平台，支持在线播放等功能，开发中...

💖 [频道别名收集计划](https://github.com/Guovin/iptv-api/discussions/1082)

- [✅ 核心特性](#核心特性)
- [🔗 最新结果](#最新结果)
- [⚙️ 配置参数](#配置)
- [🚀 快速上手](#快速上手)
    - [目录说明](#目录说明)
    - [工作流](#工作流)
    - [命令行](#命令行)
    - [GUI软件](#GUI-软件)
    - [Docker](#Docker)
- [📖 详细教程](./docs/tutorial.md)
- [🗓️ 更新日志](./CHANGELOG.md)
- [❤️ 赞赏](#赞赏)
- [👀 关注公众号](#关注)
- [⭐️ Star统计](#Star统计)
- [📣 免责声明](#免责声明)
- [⚖️ 许可证](#许可证)

> [!IMPORTANT]
> 1. 默认数据源，如订阅源，来源于Github开源项目，仅供示例作用，可能出现稳定性问题
> 2. 本项目不提供对接口结果稳定性的保证与解释
> 3. 若要实现最佳的稳定性，建议自行维护数据源

<details>
  <summary>默认数据源</summary>

📍订阅源来自：

- [Guovin/iptv-database](https://github.com/Guovin/iptv-database)
- [iptv-org/iptv](https://github.com/iptv-org/iptv)
- [suxuang/myIPTV](https://github.com/suxuang/myIPTV)
- [kimwang1978/collect-tv-txt](https://github.com/kimwang1978/collect-tv-txt)
- [vbskycn/iptv](https://github.com/vbskycn/iptv)

📍频道图标来自：

- [fanmingming/live](https://github.com/fanmingming/live)

</details>

## 核心特性

| 功能           | 支持状态 | 说明                                           |
|:-------------|:----:|:---------------------------------------------|
| **自定义模板**    |  ✅   | 生成您想要的个性化频道                                  |
| **频道别名**     |  ✅   | 提升频道结果获取量与准确率，支持正则表达式                        |
| **多种源获取方式**  |  ✅   | 支持本地源、组播源、酒店源、订阅源、关键字搜索                      |
| **RTMP推流**   |  ✅   | 支持Live与HLS模式，提升直播播放体验                        |
| **回放类接口**    |  ✅   | 支持回放类接口的获取与生成                                |
| **EPG电子节目单** |  ✅   | 显示频道预告内容                                     |
| **频道台标**     |  ✅   | 支持自定义频道台标库来源                                 |
| **接口测速验效**   |  ✅   | 获取延迟、速率、分辨率，并过滤无效接口                          |
| **高级偏好设置**   |  ✅   | IPv4/IPv6、接口排序优先级、数量配置、黑白名单、归属地与运营商过滤        |
| **定时任务**     |  ✅   | 默认北京时间每日 6:00 与 18:00 自动更新，可自定义时间或间歇更新       |
| **多种运行方式**   |  ✅   | 支持工作流、命令行、GUI 软件、Docker (amd64/arm64/arm v7) |
| **更多功能**     |  ✨   | 详见[配置参数](#配置)章节                              |

## 最新结果

> [!IMPORTANT]\
> 以下地址国内可能无法稳定访问，推荐在前拼接代理地址使用，公众号可回复`cdn`获取

### 直播源

- 默认

```bash
https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u
```

- IPv6

```bash
https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv6/result.m3u
```

- IPv4

```bash
https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u
```

### 点播源

```bash
https://raw.githubusercontent.com/Guovin/iptv-api/gd/source.json
```

## 配置

> [!NOTE]\
> 以下配置项位于`config/config.ini`文件中，支持通过配置文件或环境变量(配置项同名)实现修改，修改保存后重启即可生效

| 配置项                    | 描述                                                                                                                                                                    | 默认值               |
|:-----------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------|
| open_driver            | 开启浏览器运行，若更新无数据可开启此模式，较消耗性能                                                                                                                                            | False             |
| open_epg               | 开启EPG功能，支持频道显示预告内容                                                                                                                                                    | True              |
| open_empty_category    | 开启无结果频道分类，自动归类至底部                                                                                                                                                     | False             |
| open_filter_resolution | 开启分辨率过滤，低于最小分辨率（min_resolution）的接口将会被过滤，GUI用户需要手动安装FFmpeg，程序会自动调用FFmpeg获取接口分辨率，推荐开启，虽然会增加测速阶段耗时，但能更有效地区分是否可播放的接口                                                      | True              |                                                                                                                                                    |
| open_filter_speed      | 开启速率过滤，低于最小速率（min_speed）的接口将会被过滤                                                                                                                                      | True              |
| open_hotel             | 开启酒店源功能，关闭后所有酒店源工作模式都将关闭                                                                                                                                              | False             |
| open_hotel_foodie      | 开启 Foodie 酒店源工作模式                                                                                                                                                     | True              |
| open_hotel_fofa        | 开启 FOFA、ZoomEye 酒店源工作模式                                                                                                                                               | False             |
| open_local             | 开启本地源功能，将使用模板文件与本地源文件中的数据                                                                                                                                             | True              |
| open_m3u_result        | 开启转换生成 m3u 文件类型结果链接，支持显示频道图标                                                                                                                                          | True              |
| open_multicast         | 开启组播源功能，关闭后所有组播源工作模式都将关闭                                                                                                                                              | False             |
| open_multicast_foodie  | 开启 Foodie 组播源工作模式                                                                                                                                                     | True              |
| open_multicast_fofa    | 开启 FOFA 组播源工作模式                                                                                                                                                       | False             |
| open_online_search     | 开启关键字搜索源功能                                                                                                                                                            | False             |
| open_request           | 开启查询请求，数据来源于网络（仅针对酒店源与组播源）                                                                                                                                            | False             |
| open_rtmp              | 开启RTMP推流功能，需要安装FFmpeg，利用本地带宽提升接口播放体验                                                                                                                                  | False             |
| open_service           | 开启页面服务，用于控制是否启动结果页面服务；如果使用青龙等平台部署，有专门设定的定时任务，需要更新完成后停止运行，可以关闭该功能                                                                                                      | True              |
| open_speed_test        | 开启测速功能，获取响应时间、速率、分辨率                                                                                                                                                  | True              |
| open_subscribe         | 开启订阅源功能                                                                                                                                                               | False             |
| open_supply            | 开启补偿机制模式，用于控制当频道接口数量不足时，自动将不满足条件（例如低于最小速率）但可能可用的接口添加至结果中，从而避免结果为空的情况                                                                                                  | True              |
| open_update            | 开启更新，用于控制是否更新接口，若关闭则所有工作模式（获取接口和测速）均停止                                                                                                                                | True              |
| open_update_time       | 开启显示更新时间                                                                                                                                                              | True              |
| open_url_info          | 开启显示接口说明信息，用于控制是否显示接口来源、分辨率、协议类型等信息，为$符号后的内容，播放软件使用该信息对接口进行描述，若部分播放器（如PotPlayer）不支持解析导致无法播放可关闭                                                                        | False             |
| open_use_cache         | 开启使用本地缓存数据，适用于查询请求失败场景（仅针对酒店源与组播源）                                                                                                                                    | True              |
| open_history           | 开启使用历史更新结果（包含模板与结果文件的接口），合并至本次更新中                                                                                                                                     | True              |
| open_headers           | 开启使用M3U内含的请求头验证信息，用于测速等操作，注意：只有个别播放器支持播放这类含验证信息的接口，默认为关闭                                                                                                              | False             |
| app_port               | 页面服务端口，用于控制页面服务的端口号                                                                                                                                                   | 8000              |
| cdn_url                | CDN代理加速地址，用于订阅源、频道图标等资源的加速访问                                                                                                                                          |                   |
| final_file             | 生成结果文件路径                                                                                                                                                              | output/result.txt |
| hotel_num              | 结果中偏好的酒店源接口数量                                                                                                                                                         | 10                |
| hotel_page_num         | 酒店地区获取分页数量                                                                                                                                                            | 1                 |
| hotel_region_list      | 酒店源地区列表，"全部"表示所有地区                                                                                                                                                    | 全部                |
| isp                    | 接口运营商，用于控制结果中只包含填写的运营商类型，支持关键字过滤，英文逗号分隔，不填写表示不指定运营商                                                                                                                   |                   |
| ipv4_num               | 结果中偏好的 IPv4 接口数量                                                                                                                                                      | 5                 |
| ipv6_num               | 结果中偏好的 IPv6 接口数量                                                                                                                                                      | 5                 |
| ipv6_support           | 强制认为当前网络支持IPv6，跳过检测                                                                                                                                                   | False             |
| ipv_type               | 生成结果中接口的协议类型，可选值：ipv4、ipv6、全部、all                                                                                                                                     | 全部                |
| ipv_type_prefer        | 接口协议类型偏好，优先将该类型的接口排在结果前面，可选值：ipv4、ipv6、自动、auto                                                                                                                        | ipv6,ipv4         |
| location               | 接口归属地，用于控制结果只包含填写的归属地类型，支持关键字过滤，英文逗号分隔，不填写表示不指定归属地，建议使用靠近使用者的归属地，能提升播放体验                                                                                              |                   |
| local_file             | 本地源文件路径                                                                                                                                                               | config/local.txt  |
| local_num              | 结果中偏好的本地源接口数量                                                                                                                                                         | 10                |
| logo_url               | 频道台标库地址                                                                                                                                                               |                   |
| logo_type              | 频道台标文件类型                                                                                                                                                              | png               |
| min_resolution         | 接口最小分辨率，需要开启 open_filter_resolution 才能生效                                                                                                                              | 1920x1080         |
| max_resolution         | 接口最大分辨率，需要开启 open_filter_resolution 才能生效                                                                                                                              | 1920x1080         |
| min_speed              | 接口最小速率（单位M/s），需要开启 open_filter_speed 才能生效                                                                                                                             | 0.5               |
| multicast_num          | 结果中偏好的组播源接口数量                                                                                                                                                         | 10                |
| multicast_page_num     | 组播地区获取分页数量                                                                                                                                                            | 1                 |
| multicast_region_list  | 组播源地区列表，"全部"表示所有地区                                                                                                                                                    | 全部                |
| online_search_num      | 结果中偏好的关键字搜索接口数量                                                                                                                                                       | 0                 |
| online_search_page_num | 关键字搜索频道获取分页数量                                                                                                                                                         | 1                 |
| origin_type_prefer     | 结果偏好的接口来源，结果优先按该顺序进行排序，逗号分隔，例如：local,hotel,multicast,subscribe,online_search；local：本地源，hotel：酒店源，multicast：组播源，subscribe：订阅源，online_search：关键字搜索；不填写则表示不指定来源，按照接口速率排序 |                   |
| recent_days            | 获取最近时间范围内更新的接口（单位天），适当减小可避免出现匹配问题                                                                                                                                     | 30                |
| request_timeout        | 查询请求超时时长，单位秒(s)，用于控制查询接口文本链接的超时时长以及重试时长，调整此值能优化更新时间                                                                                                                   | 10                |
| speed_test_limit       | 同时执行测速的接口数量，用于控制测速阶段的并发数量，数值越大测速所需时间越短，负载较高，结果可能不准确；数值越小测速所需时间越长，低负载，结果较准确；调整此值能优化更新时间                                                                                | 10                |
| speed_test_timeout     | 单个接口测速超时时长，单位秒(s)；数值越大测速所需时间越长，能提高获取接口数量，但质量会有所下降；数值越小测速所需时间越短，能获取低延时的接口，质量较好；调整此值能优化更新时间                                                                             | 10                |
| speed_test_filter_host | 测速阶段使用Host地址进行过滤，相同Host地址的频道将共用测速数据，开启后可大幅减少测速所需时间，但可能会导致测速结果不准确                                                                                                      | False             |
| source_file            | 模板文件路径                                                                                                                                                                | config/demo.txt   |
| subscribe_num          | 结果中偏好的订阅源接口数量                                                                                                                                                         | 10                |
| time_zone              | 时区，可用于控制更新时间显示的时区，可选值：Asia/Shanghai 或其它时区编码                                                                                                                           | Asia/Shanghai     |
| urls_limit             | 单个频道接口数量                                                                                                                                                              | 10                |
| update_interval        | 定时执行更新时间间隔，单位小时，设置0或空则只运行一次，不作用于工作流                                                                                                                                   | 12                |
| update_time_position   | 更新时间显示位置，需要开启 open_update_time 才能生效，可选值：top、bottom，top:显示于结果顶部，bottom: 显示于结果底部                                                                                        | top               |

## 快速上手

### 目录说明

| 目录路径                      | 说明                  |
|:--------------------------|:--------------------|
| config                    | 配置文件目录，包含配置文件、模板文件等 |
| config/config.ini         | 配置参数文件              |
| config/rtp                | 各地区运营商组播源ip         |
| config/demo.txt           | 频道模板                |
| config/alias.txt          | 频道别名                |
| config/blacklist.txt      | 接口黑名单               |
| config/whitelist.txt      | 接口白名单               |
| config/subscribe.txt      | 频道订阅源列表             |
| config/local.txt          | 本地源文件               |
| config/epg.txt            | EPG订阅源列表            |
| output                    | 结果文件目录，包含生成的结果文件等   |
| output/data               | 结果数据缓存目录            |
| output/epg                | EPG结果目录             |
| output/ipv4               | IPv4结果目录            |
| output/ipv6               | IPv6结果目录            |
| output/result(.m3u/txt)   | m3u/txt结果           |
| output/live(.m3u/txt)     | RTMP推流live结果        |
| output/hls(.m3u/txt)      | RTMP推流hls结果         |
| output/log                | 日志文件目录              |
| output/log/result.log     | 有效结果日志              |
| output/log/speed_test.log | 测速日志                |
| output/log/statistic.log  | 统计结果日志              |
| output/log/nomatch.log    | 未匹配频道记录             |
| source.json               | 点播源配置文件             |

### 工作流

Fork 本项目并开启工作流更新，具体步骤请见[详细教程](./docs/tutorial.md)

### 命令行

```shell
pip install pipenv
```

```shell
pipenv install --dev
```

启动更新：

```shell
pipenv run dev
```

启动服务：

```shell
pipenv run service
```

### GUI 软件

1. 下载[IPTV-API 更新软件](https://github.com/Guovin/iptv-api/releases)，打开软件，点击启动，即可进行更新

2. 或者在项目目录下运行以下命令，即可打开 GUI 软件：

```shell
pipenv run ui
```

<img src="./docs/images/ui.png" alt="IPTV-API更新软件" title="IPTV-API更新软件" style="height:600px" />

### Docker

#### 1. 拉取镜像

```bash
docker pull guovern/iptv-api:latest
```

🚀 代理加速（推荐国内用户使用）：

```bash
docker pull docker.1ms.run/guovern/iptv-api:latest
```

#### 2. 运行容器

```bash
docker run -d -p 8000:8000 guovern/iptv-api
```

##### 挂载（推荐）：

实现宿主机文件与容器文件同步，修改模板、配置、获取更新结果文件可直接在宿主机文件夹下操作

以宿主机路径/etc/docker 为例：

```bash
-v /etc/docker/config:/iptv-api/config
-v /etc/docker/output:/iptv-api/output
```

##### 环境变量：

| 变量       | 描述                 | 默认值                |
|:---------|:-------------------|:-------------------|
| APP_HOST | 服务host地址，可修改使用公网域名 | "http://localhost" |
| APP_PORT | 服务端口               | 8000               |

#### 3. 更新结果

| 接口              | 描述          |
|:----------------|:------------|
| /               | 默认接口        |
| /m3u            | m3u 格式接口    |
| /txt            | txt 格式接口    |
| /ipv4           | ipv4 默认接口   |
| /ipv6           | ipv6 默认接口   |
| /ipv4/txt       | ipv4 txt接口  |
| /ipv6/txt       | ipv6 txt接口  |
| /ipv4/m3u       | ipv4 m3u接口  |
| /ipv6/m3u       | ipv6 m3u接口  |
| /content        | 接口文本内容      |
| /log/result     | 有效结果的日志     |
| /log/speed-test | 所有参与测速接口的日志 |
| /log/statistic  | 统计结果的日志     |
| /log/nomatch    | 未匹配频道的日志    |

- RTMP 推流：

> [!NOTE]
> 1. 如果需要对本地视频源进行推流，可在`config`目录下新建`live`或`hls`（推荐）文件夹
> 2. live文件夹用于推流live接口，hls文件夹用于推流hls接口
> 3. 将以`频道名称命名`的视频文件放入其中，程序会自动推流到对应的频道中
> 4. 可访问 http://localhost:8080/stat 查看实时推流状态统计数据

| 推流接口           | 描述                |
|:---------------|:------------------|
| /live          | 推流live接口          |
| /hls           | 推流hls接口           |
| /live/txt      | 推流live txt接口      |
| /hls/txt       | 推流hls txt接口       |
| /live/m3u      | 推流live m3u接口      |
| /hls/m3u       | 推流hls m3u接口       |
| /live/ipv4/txt | 推流live ipv4 txt接口 |
| /hls/ipv4/txt  | 推流hls ipv4 txt接口  |
| /live/ipv4/m3u | 推流live ipv4 m3u接口 |
| /hls/ipv4/m3u  | 推流hls ipv4 m3u接口  |
| /live/ipv6/txt | 推流live ipv6 txt接口 |
| /hls/ipv6/txt  | 推流hls ipv6 txt接口  |
| /live/ipv6/m3u | 推流live ipv6 m3u接口 |
| /hls/ipv6/m3u  | 推流hls ipv6 m3u接口  |

## 更新日志

[更新日志](./CHANGELOG.md)

## 赞赏

<div>开发维护不易，请我喝杯咖啡☕️吧~</div>

| 支付宝                                  | 微信                                      |
|--------------------------------------|-----------------------------------------|
| ![支付宝扫码](./static/images/alipay.jpg) | ![微信扫码](./static/images/appreciate.jpg) |

## 关注

微信公众号搜索 Govin，或扫码，接收更新推送、学习更多使用技巧：

![微信公众号](./static/images/qrcode.jpg)

## Star统计

[![Star统计](https://api.star-history.com/svg?repos=Guovin/iptv-api&type=Date)](https://star-history.com/#Guovin/iptv-api&Date)

## 免责声明

本项目仅供学习交流用途，接口数据均来源于网络，如有侵权，请联系删除

## 许可证

[MIT](./LICENSE) License &copy; 2024-PRESENT [Govin](https://github.com/guovin)

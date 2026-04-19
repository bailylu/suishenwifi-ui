# 随身WiFi 配网 & 管理系统

为高通 410 随身WiFi 设备打造的完整配网与管理方案。设备开机自动尝试连接已知 WiFi，若连接失败则开启热点并弹出配网门户；联网后提供 Web 后台管理界面，支持短信收件箱、WiFi 切换、Bark 推送配置。

## 功能

- **Captive Portal 配网**：手机连热点自动弹出配网页面，填写 WiFi 和 Bark 信息后设备自动重启联网
- **Bark 推送**：联网成功后推送 IP 地址和后台管理链接
- **Web 后台管理**：浏览器访问设备 IP，查看设备状态、短信收件箱、转发记录，在线切换 WiFi、配置 Bark
- **短信转发**：收到短信自动通过 Bark 推送到手机
- **自动兜底**：开机 40 秒未联网自动切热点；10 分钟蜂窝未注册自动重启

## 硬件要求

- 高通 410（MSM8916）随身WiFi 设备
- 已刷入 ARM Debian 或 ARM Ubuntu（见下方刷机说明）
- 已插入 SIM 卡

## 刷机说明

> 如果你的设备已经运行 Linux 系统，跳过此节直接看「安装」。

### 推荐固件

社区维护的高通 410 随身WiFi Debian 镜像，支持 NetworkManager、ModemManager、mmcli。

### 刷机步骤（以 Windows 为例）

1. 下载 [Qualcomm USB Driver](https://developer.qualcomm.com/software/usb-drivers) 并安装
2. 设备关机，按住复位键同时插入 USB，进入 EDL（9008）模式
   - 设备管理器中出现 `Qualcomm HS-USB QDLoader 9008` 即成功
3. 使用 [QFIL](https://qfil.en.softonic.com/) 或 `edl` 工具烧录固件：
   ```
   edl qfil --image debian-arm64.img
   ```
4. 拔插 USB，设备正常启动后通过 USB 串口或 ADB 获取 shell

### 首次 SSH 连接

设备默认通过 USB RNDIS 共享网络，IP 通常为 `192.168.3.22` 或 `192.168.100.1`：

```bash
ssh root@192.168.3.22
# 或
ssh root@192.168.100.1
```

## 安装

### 方式一：一键安装（推荐）

```bash
# 1. 下载项目
git clone https://github.com/YOUR_GITHUB/suishenwifi.git
cd suishenwifi

# 2. 上传到设备（在你的电脑上执行）
scp -r . root@192.168.3.22:/tmp/suishenwifi/

# 3. SSH 进设备执行安装
ssh root@192.168.3.22
cd /tmp/suishenwifi

# 最简安装（首次配网走热点门户）
bash install.sh

# 带参数安装（预填 Bark + WiFi，安装后直接可用）
bash install.sh https://api.day.app 你的BarkKey 你的WiFi名称 你的WiFi密码
```

### 方式二：curl 一键（设备已联网时）

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB/suishenwifi/main/install.sh | bash
```

### 安装参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `$1` BARK_SERVER | Bark 服务地址 | `https://api.day.app` |
| `$2` BARK_KEY | Bark 推送 Key | `AbCdEfGhIjKlMn` |
| `$3` WIFI_SSID | 上行 WiFi 名称（可选） | `MyHomeWiFi` |
| `$4` WIFI_PASS | 上行 WiFi 密码（可选） | `password123` |

安装完成后执行 `reboot` 重启设备。

## 使用流程

### 首次配网

```
设备开机
  └─ 尝试连接已知 WiFi（40秒）
       ├─ 成功 → Bark 推送「随身WiFi已联网 后台管理：http://IP」
       └─ 失败 → 开启热点「suishenWiFi」（无密码）
                  └─ 手机连接热点 → 自动弹出配网页面
                       └─ 填写 WiFi名称 + 密码 + Bark地址 → 提交
                            └─ 设备重启 → 连接WiFi → Bark 推送 ✅
```

### 日常使用

1. 收到 Bark 推送后，点击通知中的链接打开后台管理页面
2. 后台可查看：设备状态、短信收件箱、转发记录
3. 后台可操作：切换 WiFi、修改 Bark 配置、发送测试推送

## 文件结构

```
install.sh                          # 一键安装脚本
opt/
  captive-portal/
    portal.py                       # 配网门户 Web 服务（AP 模式，端口 80）
    cp-setup.sh                     # AP 模式 iptables 规则
    cp-teardown.sh                  # 清理 iptables 规则
    bark-notify.sh                  # 联网后推送 Bark 通知
    provision-watchdog.sh           # 开机 40s 兜底切热点
    modem-watchdog.sh               # 开机 10min 蜂窝未注册则重启
  admin/
    admin.py                        # 后台管理 Web 服务（STA 模式，端口 80）
etc/
  systemd/system/
    captive-portal.service          # 由 NM dispatcher 管理，勿手动 enable
    admin-panel.service             # STA 模式下运行
    bark-notify.service             # 开机一次性推送
    provision-watchdog.service      # 开机一次性看门狗
    modem-watchdog.service          # 开机一次性蜂窝看门狗
  NetworkManager/
    dispatcher.d/99-portal          # AP/STA 切换时启停服务
    dnsmasq-shared.d/captive.conf   # DNS 全劫持（AP 模式弹窗用）
sms_forwarder.sh                    # 短信转发脚本（读 /etc/bark.conf）
```

## 配置文件

### /etc/bark.conf

```bash
BARK_SERVER="https://api.day.app"
BARK_KEY="你的BarkKey"
```

安装后可通过后台管理页面在线修改，无需 SSH。

## 常见问题

**Q：手机连上热点后没有自动弹出配网页面？**  
A：部分机型需要手动打开浏览器访问 `http://10.42.1.1`。

**Q：提交配网信息后设备没有重启？**  
A：等待约 3 秒，设备会自动重启。如未重启请手动执行 `reboot`。

**Q：配网后收不到 Bark 推送？**  
A：检查 Bark Key 是否正确，可在后台管理页面发送测试推送验证。

**Q：蜂窝信号一直显示为空？**  
A：SIM 初始化最长需要约 3 分钟，稍等后刷新后台页面即可。

**Q：如何重置回初始配网状态？**  
```bash
nmcli c delete <当前WiFi名称>
rm -f /var/lib/captive-portal/last_failed
reboot
```

## 技术说明

- **配网门户原理**：AP 模式下 dnsmasq 将所有 DNS 劫持到 `10.42.1.1`，portal.py 监听 80 端口，对非门户请求返回 302 跳转触发 iOS/Android 系统弹窗；443 端口发送 TCP RST 让手机快速降级到 HTTP 探测
- **服务互斥**：captive-portal（端口 80）和 admin-panel（端口 80）通过 NM dispatcher 互斥启停，AP 模式跑门户，STA 模式跑后台
- **热点自动切换**：`suishenwifi` profile 设置 `autoconnect=no`，只由 provision-watchdog 在判断 STA 失败后手动激活，避免设备卡在热点模式出不来

## License

MIT

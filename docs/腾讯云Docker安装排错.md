# 腾讯云 Docker 安装排错

更新日期：2026-03-16

适用场景：

- 腾讯云 CVM
- Ubuntu 22.04 / 24.04
- 按 Docker 官方仓库方式安装时，出现下面两类报错：
  - `chmod: cannot access '/etc/apt/keyrings/docker.asc': No such file or directory`
  - `Package docker-ce is not available` / `Unable to locate package docker-ce-cli`

## 1. 问题原因

这两个报错通常不是 Docker 包本身坏了，而是 Docker APT 仓库没有真正加成功。

常见原因有：

1. `curl` 下载 GPG key 失败，所以 `/etc/apt/keyrings/docker.asc` 根本没生成。
2. `docker.list` 没写进去，或者写入内容不对。
3. `apt update` 时没有成功读取 Docker 官方仓库。
4. 服务器到 `download.docker.com` 的网络不稳定。

## 2. 推荐安装方式

比起直接下载 `docker.asc` 原文件，我更建议你用 `gpg --dearmor` 的方式，兼容性更稳。

先完整执行下面这组命令：

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 3. 如果还是失败，按这个顺序检查

### 3.1 检查 GPG key 文件是否真的存在

```bash
ls -l /etc/apt/keyrings/
```

你至少应该能看到：

- `docker.gpg`

如果没有，说明 `curl | gpg --dearmor` 这一步失败了。

### 3.2 检查 Docker 仓库文件是否存在

```bash
cat /etc/apt/sources.list.d/docker.list
```

正常应该类似：

```text
deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu jammy stable
```

如果你是 Ubuntu 24.04，最后可能是 `noble stable`。

### 3.3 检查系统版本代号

```bash
. /etc/os-release && echo $VERSION_CODENAME
```

Ubuntu 22.04 应该是：

```text
jammy
```

Ubuntu 24.04 应该是：

```text
noble
```

### 3.4 检查 apt 是否真的读到了 Docker 仓库

```bash
sudo apt update
apt-cache policy docker-ce
```

如果输出里没有 candidate，基本就说明 Docker 仓库还是没加成功。

### 3.5 检查服务器到 Docker 官方仓库的网络

```bash
curl -I https://download.docker.com/linux/ubuntu/
```

如果这里超时、握手失败、连接中断，那就不是命令写错，而是服务器网络到 Docker 官方源不稳定。

## 4. 你刚才两个报错分别意味着什么

### 报错 1

```text
chmod: cannot access '/etc/apt/keyrings/docker.asc': No such file or directory
```

这说明前一步并没有成功生成 `/etc/apt/keyrings/docker.asc`。

也就是说，不要继续往后装 `docker-ce`，因为仓库签名文件都还没准备好。

### 报错 2

```text
Package docker-ce is not available
Unable to locate package docker-ce-cli
```

这说明：

- `apt` 当前只看到了 Ubuntu 默认仓库
- 没有成功看到 Docker 官方仓库

所以它根本找不到这些包。

## 5. 一条更稳的最小排错路径

你现在可以直接按这组命令来，不要跳步：

```bash
sudo rm -f /etc/apt/sources.list.d/docker.list
sudo rm -f /etc/apt/keyrings/docker.asc
sudo rm -f /etc/apt/keyrings/docker.gpg

sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

cat /etc/apt/sources.list.d/docker.list
sudo apt update
apt-cache policy docker-ce
```

只有在 `apt-cache policy docker-ce` 能看到 candidate 之后，再执行：

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 6. 如果 Docker 官方源还是不通

在腾讯云机器上，如果到 `download.docker.com` 不稳定，可以考虑：

1. 先使用腾讯云或国内可访问的软件源方案。
2. 先安装系统自带的 `docker.io` 作为临时方案。
3. 真正上线时，再切回官方 Docker Engine。

临时方案命令：

```bash
sudo apt update
sudo apt install -y docker.io
```

然后看系统里是否有 Compose 插件：

```bash
docker --version
docker compose version
```

如果 `docker compose` 不可用，再看是否需要额外安装 Compose 插件。

注意：这是临时兜底方案，不是我最推荐的长期方案。

## 7. 下一步怎么继续

你现在最应该做的是，把下面 4 条命令的输出发出来：

```bash
ls -l /etc/apt/keyrings/
cat /etc/apt/sources.list.d/docker.list
. /etc/os-release && echo $VERSION_CODENAME
apt-cache policy docker-ce
```

有了这 4 个结果，就能非常快判断是：

- GPG key 没写成功
- Docker 仓库没写成功
- 系统版本代号不对
- 还是纯网络问题

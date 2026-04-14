# 腾讯云 CVM 部署指南

更新日期：2026-03-14

本文基于当前仓库现状编写，默认部署目标为：

- 云平台：腾讯云 CVM
- 操作系统：Ubuntu 22.04 LTS
- 部署方式：CVM + Docker Compose + 宿主机 Nginx + HTTPS
- 项目结构：前端容器监听 `127.0.0.1:8080`，后端容器监听 `127.0.0.1:8000`

## 1. 先说结论

对你这个项目，最推荐的腾讯云方案是：

1. 购买一台 Ubuntu 的 CVM
2. 在 CVM 上安装 Docker Engine 和 Docker Compose 插件
3. 拉取当前仓库代码
4. 配置 `backend/.env`
5. 用 Docker Compose 启动前后端
6. 在宿主机安装 Nginx，把 80/443 转发到 `127.0.0.1:8080`
7. 绑定域名并配置 HTTPS

原因是这套方案和你当前仓库最匹配，MCP 子进程、前端静态资源、反向代理都能保持简单稳定。

## 2. 当前 Docker 配置检查结论

当前 Docker 配置整体是可以上云的，结论如下：

- `docker-compose.yml` 结构合理，前后端分为两个服务。
- 前端容器只暴露给宿主机 `127.0.0.1:8080`，后端只暴露给宿主机 `127.0.0.1:8000`，适合外层再挂 Nginx。
- `frontend/nginx.conf` 已经能把 `/api/` 代理到 `backend:8000`。
- 我已经把 `frontend/Dockerfile` 改成基于 `package-lock.json` 执行 `npm ci`，部署更稳定。
- 我已经补了 `frontend/.dockerignore` 和 `backend/.dockerignore`，减少无关文件进入构建上下文。

当前需要你注意的只有一点：

- 如果腾讯云服务器也拉不到 Docker Hub，就要继续使用 `.env.docker` 覆盖基础镜像，或者改用腾讯云 TCR 托管镜像。

## 3. 第一步：购买腾讯云 CVM

建议配置：

- 地域：选择离主要用户近的地域，例如广州、上海、北京
- 镜像：Ubuntu 22.04 LTS
- 规格：2核4G 起步
- 系统盘：40GB SSD 起步
- 公网 IP：开启
- 带宽：按量或包月均可，起步 3Mbps - 5Mbps

如果这是第一个正式版本，2核4G 足够；如果后面会频繁跑多用户请求，建议直接 4核8G。

腾讯云官方关于 CVM 的登录和安全组文档：

- 使用 SSH 登录 Linux 实例：<https://cloud.tencent.com/document/product/213/35700>
- 配置安全组：<https://cloud.tencent.com/document/product/213/15377>

## 4. 第二步：配置安全组

在腾讯云控制台里，至少放通这些端口：

- `22`：SSH 登录
- `80`：HTTP
- `443`：HTTPS

建议不要直接开放 `8000` 和 `8080` 到公网，因为当前 Compose 已经只绑定到 `127.0.0.1`，也没必要开放。

腾讯云官方说明中，`22`、`80`、`443` 都属于标准 Web 场景推荐放通端口。这是我根据官方安全组文档做出的部署建议。

## 5. 第三步：SSH 登录服务器

在本地终端执行：

```bash
ssh ubuntu@你的服务器公网IP
```

如果你使用的是 root 用户镜像，也可能是：

```bash
ssh root@你的服务器公网IP
```

腾讯云官方文档说明 Ubuntu 默认账号通常为 `ubuntu`，也可能因镜像不同而不同，请以控制台信息为准。

## 6. 第四步：安装基础软件

登录后先执行：

```bash
sudo apt update
sudo apt install -y git curl ca-certificates nginx
```

这里先把 `nginx` 一起装上，后面直接接 HTTPS。

## 7. 第五步：安装 Docker Engine

推荐直接按 Docker 官方 Ubuntu 文档安装：

- Docker Ubuntu 安装文档：<https://docs.docker.com/engine/install/ubuntu/>

按官方文档，核心步骤是：

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

验证：

```bash
docker --version
docker compose version
sudo systemctl status docker
```

## 8. 第六步：拉取项目代码

推荐放在 `/opt`：

```bash
cd /opt
sudo git clone <你的仓库地址> trip-planning-agent
sudo chown -R $USER:$USER /opt/trip-planning-agent
cd /opt/trip-planning-agent
```

## 9. 第七步：准备生产环境变量

### 后端

复制模板：

```bash
cp backend/.env.production.example backend/.env
```

然后编辑：

```bash
nano backend/.env
```

至少要填这些值：

- `CORS_ORIGINS`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `AMAP_API_KEY`
- `AMAP_SECURITY_JS_CODE`
- `AMAP_MCP_ENV` 里的 `AMAP_MAPS_API_KEY`

你正式部署时，建议至少改成：

```env
APP_ENV=production
ENABLE_MOCK_MCP=false
CORS_ORIGINS=["https://travel.yourdomain.com"]
```

### 前端

当前仓库已经有：

- `frontend/.env.production`

它默认是：

```env
VITE_API_BASE_URL=
VITE_SHOW_DEV_PANELS=false
```

这个值适合你当前的前后端同域部署，不需要再额外改。

## 10. 第八步：如果服务器拉 Docker Hub 慢

这是你本地已经遇到过的问题，腾讯云服务器上也有可能碰到。

你有两种选择：

### 方式 A：继续使用 `.env.docker`

如果 CVM 也拉不动 Docker Hub，就在服务器上复制并编辑：

```bash
cp .env.docker.example .env.docker
nano .env.docker
```

然后用：

```bash
docker compose --env-file .env.docker up -d --build
```

### 方式 B：使用腾讯云 TCR

腾讯云官方产品文档：

- TCR 文档入口：<https://cloud.tencent.com/document/product/1141/>
- TCR 产品页：<https://cloud.tencent.com/product/tcr>

根据腾讯云官方介绍，TCR 适合做镜像托管和就近分发。如果你后面准备长期上线，我建议把自己的前后端镜像推到 TCR，再在 CVM 上直接拉你自己的镜像，而不是每次临时从公共仓库构建。

这是我基于腾讯云 TCR 官方产品文档做出的推荐。

## 11. 第九步：启动 Docker Compose

如果服务器能直接访问 Docker Hub：

```bash
docker compose up -d --build
```

如果你在用自定义镜像覆盖：

```bash
docker compose --env-file .env.docker up -d --build
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

## 12. 第十步：先做本机验收

先不要急着对外开放域名，先在服务器本机验证。

### 健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### 集成状态检查

```bash
curl http://127.0.0.1:8000/api/v1/plans/integrations/status
```

### 前端检查

```bash
curl http://127.0.0.1:8080
```

如果这三步正常，说明容器基本没问题。

## 13. 第十一步：配置域名解析

如果域名在腾讯云 DNSPod 管理，推荐加一条 A 记录：

- 主机记录：`travel`
- 记录类型：`A`
- 记录值：你的 CVM 公网 IP

腾讯云官方文档：

- 快速添加域名解析：<https://cloud.tencent.com/document/product/302/3446>
- A 记录说明：<https://cloud.tencent.com/document/product/302/3449>

## 14. 第十二步：配置宿主机 Nginx

当前仓库已经给你准备了示例配置：

- `deploy/tencent-cvm-nginx.example.conf`

你可以把它复制到服务器，例如：

```bash
sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
sudo cp /opt/trip-planning-agent/deploy/tencent-cvm-nginx.example.conf /etc/nginx/sites-available/trip-planning-agent.conf
```

然后编辑域名和证书路径：

```bash
sudo nano /etc/nginx/sites-available/trip-planning-agent.conf
```

建立软链接：

```bash
sudo ln -s /etc/nginx/sites-available/trip-planning-agent.conf /etc/nginx/sites-enabled/trip-planning-agent.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 15. 第十三步：配置 HTTPS

你有两条路：

### 路线 A：腾讯云 SSL 证书

腾讯云官方文档：

- 免费 SSL 证书概述：<https://cloud.tencent.com/document/product/400/89868>
- Nginx Linux 安装 SSL 证书：<https://cloud.tencent.com/document/product/400/35244>

如果你在腾讯云申请了证书，下载 Nginx 版本证书文件后，把证书放到服务器，例如：

```bash
sudo mkdir -p /etc/nginx/ssl
```

把证书和私钥放到：

- `/etc/nginx/ssl/travel.yourdomain.com_bundle.crt`
- `/etc/nginx/ssl/travel.yourdomain.com.key`

然后更新 Nginx 配置并 reload。

### 路线 B：使用 Certbot

Certbot 官方站点：<https://certbot.eff.org/>

如果你用 Let’s Encrypt，也可以在服务器上直接签发证书。这个方案更省钱，但证书续期需要额外确认自动化任务正常。

## 16. 第十四步：正式验收

正式验收时，按这个顺序检查：

1. `http://你的域名` 是否能自动跳转到 HTTPS
2. `https://你的域名` 首页是否能打开
3. 是否能正常提交规划请求
4. 地图是否能加载
5. `/api/v1/plans/integrations/status` 是否正常
6. MCP 是否为连接状态
7. 大模型是否为可用状态

## 17. 第十五步：后续发布方式

以后每次发版，流程基本固定：

```bash
cd /opt/trip-planning-agent
git pull
docker compose up -d --build
```

如果你用了 `.env.docker`：

```bash
cd /opt/trip-planning-agent
git pull
docker compose --env-file .env.docker up -d --build
```

## 18. 我的建议

如果你现在准备真正上腾讯云，我建议你按这个顺序做：

1. 先买 CVM 并放通 22/80/443
2. 登录服务器安装 Docker 和 Nginx
3. 拉代码，配置 `backend/.env`
4. 先在服务器本机跑通 `docker compose up -d --build`
5. 再绑域名
6. 最后再配 HTTPS

这样出问题时更容易定位，不会把“容器问题、域名问题、证书问题”混在一起。

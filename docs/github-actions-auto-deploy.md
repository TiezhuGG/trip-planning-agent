# GitHub Actions 自动部署说明

本文档说明如何把当前项目接入 GitHub Actions，并在 `git push` 到 `main` 后自动部署到服务器 `101.34.87.128`。

## 1. 当前部署方式

当前仓库的生产部署方式是：

- 服务器用户：`ubuntu`
- 项目目录：`/opt/trip-planning-agent`
- 代码分支：`main`
- 发布命令：

```bash
git pull && docker compose --env-file .env.docker up -d --build
```

GitHub Actions 只是把这套已验证可用的手工流程自动化，不改变服务器上的运行结构。

## 2. Workflow 触发规则

仓库新增的 workflow 文件是：

- `.github/workflows/deploy.yml`

它的行为是：

1. 当代码 `push` 到 `main` 分支时触发
2. 先在 GitHub Runner 上执行校验
3. 校验通过后，通过 SSH 登录服务器
4. 在服务器上执行拉代码和重建容器

## 3. 部署前校验内容

自动部署前会先做两类检查：

### 前端

```bash
cd frontend
npm ci
npm run build
```

### 后端

```bash
cd backend
python -m pip install -r requirements.txt
pytest -q tests
```

只要其中任何一步失败，workflow 就会停止，不会进入服务器部署阶段。

## 4. 需要配置的 GitHub Secrets

在 GitHub 仓库页面进入：

- `Settings`
- `Secrets and variables`
- `Actions`

新增以下 secrets：

### `PROD_HOST`

值：

```text
101.34.87.128
```

### `PROD_USER`

值：

```text
ubuntu
```

### `PROD_SSH_KEY`

值是 GitHub Actions 用来 SSH 登录服务器的私钥全文。

注意：

- 这个私钥对应的公钥必须已经加入服务器：

```bash
/home/ubuntu/.ssh/authorized_keys
```

- 这个 key 的用途是“GitHub Actions 登录服务器”
- 它不等同于“服务器拉 GitHub 仓库”的 deploy key

### `PROD_PORT`

可选。  
如果你服务器 SSH 端口还是默认的 `22`，这个 secret 可以不配。

如果你改过 SSH 端口，再把实际端口填进去。

## 5. 服务器需要满足的前提

Actions 自动部署依赖以下前提已经成立：

1. 服务器上的项目目录已经存在：

```bash
/opt/trip-planning-agent
```

2. `ubuntu` 用户可以在该目录手动执行：

```bash
git pull
docker compose --env-file .env.docker up -d --build
```

3. `ubuntu` 用户有 Docker 权限

通常表示这个用户已经加入 `docker` 组。

4. 服务器自身已经配置好 GitHub 拉代码凭证

因为 workflow 登录服务器后执行的仍然是服务器本机的：

```bash
git pull --ff-only origin main
```

所以服务器自己必须能访问 GitHub 仓库。

## 6. Workflow 实际执行的远程命令

workflow 登录服务器后执行的是：

```bash
cd /opt/trip-planning-agent
git fetch --all --prune
git checkout main
git pull --ff-only origin main
docker compose --env-file .env.docker up -d --build
docker compose ps
```

这意味着：

- 总是部署 `main`
- 总是基于服务器现有工作目录更新
- 部署后会输出容器状态，方便在 Actions 日志里排查

## 7. 首次启用建议

第一次启用前，建议按下面顺序检查：

1. 先确认服务器上手工部署命令仍然能跑通
2. 再配置 GitHub Secrets
3. 然后 push 一个很小的提交到 `main`
4. 打开 GitHub Actions 页面观察执行日志

建议第一次只提交一个无业务影响的小改动，例如：

- README 微调
- 文档补充

## 8. 常见失败点

### 1. SSH 登录失败

通常是以下原因：

- `PROD_SSH_KEY` 不匹配
- 公钥未加入 `authorized_keys`
- `PROD_USER` 错误
- SSH 端口配置不一致

### 2. 服务器上 `git pull` 失败

通常表示：

- 服务器本机没有 GitHub 拉取权限
- 仓库远端地址不对
- 工作目录里存在阻塞更新的本地改动

### 3. `docker compose` 执行失败

常见原因：

- `ubuntu` 没有 Docker 权限
- 服务器磁盘不足
- `.env` 或 `.env.docker` 配置缺失
- 镜像构建依赖外网失败

### 4. Workflow 根本不部署

通常是前置校验失败：

- 前端 `npm run build` 失败
- 后端 `pytest -q tests` 失败

这种情况是预期行为，表示坏提交被拦下，没有上线。

## 9. 推荐验证方式

每次修改部署链路后，至少验证一次：

1. push 到 `main`
2. GitHub Actions 成功触发
3. build 成功
4. test 成功
5. SSH 成功
6. 服务器容器成功重建
7. 浏览器访问：

```text
http://101.34.87.128:8080/
```

确认页面正常打开

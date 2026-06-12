# 🚀 基金情绪分析系统 V3.5 — 小白部署指南

> 这份指南假设你**完全不懂代码**。每一步都会告诉你：在哪里操作、点什么按钮、输入什么内容。
> 全程只需要：复制粘贴 + 点鼠标。遇到不懂的术语，都有括号解释。

---

## 前置准备（你之前已经完成的）

| 序号 | 事项 | 状态 |
|------|------|------|
| 1 | Supabase 注册 | ✅ 已完成 |
| 2 | Upstash Redis 注册 | ✅ 已完成 |
| 3 | Vercel 注册 | ✅ 已完成 |
| 4 | GitHub 仓库已创建 | ✅ 已完成 |
| 6 | Tushare 注册 | ✅ 已完成 |

---

## 第一步：把项目代码上传到 GitHub（5 分钟）

### 1.1 找到你电脑上的项目文件夹

项目文件夹名字叫 `fund-sentiment`，现在就在当前目录下。你需要先把它下载到你自己的电脑上。

**问：怎么下载？**

答：我会帮你把整个项目打包成一个压缩文件。你下载后解压到桌面就行。但更简单的方式是：

> 直接在 CodeBuddy 里说「帮我把 fund-sentiment 项目推送到我的 GitHub 仓库」，我来帮你操作。

### 1.2 推送代码到 GitHub（让我来操作）

如果你已经创建了 GitHub 仓库（比如叫 `fund-sentiment`），告诉我仓库地址（类似 `https://github.com/你的用户名/fund-sentiment`），我帮你把代码推上去。

**仓库地址在哪看？**

打开你的 GitHub 仓库页面 → 浏览器地址栏里那个网址就是，例如：
```
https://github.com/zhangsan/fund-sentiment
```

---

## 第二步：部署后端到 ECS 服务器（10 分钟）

### 2.1 创建阿里云 ECS 服务器

打开浏览器，访问：https://ecs.console.aliyun.com

**步骤：**

1. 点击页面上的 **「创建实例」** 按钮（大蓝色按钮）
2. 在创建页面，按以下内容填写：

| 选项 | 选什么 | 在哪里找 |
|------|--------|---------|
| 计费方式 | **抢占式实例** | 页面顶部，几个选项之一 |
| 地域 | **华北 2（北京）** | 下拉框里找 |
| 实例规格 | **ecs.e-c1m2.large（2vCPU 4G）** | 在列表里找，搜 "e-c1m2" |
| 镜像 | **Ubuntu 22.04** | 选"公共镜像" → 搜 "Ubuntu" → 选 22.04 |
| 系统盘 | **40GB ESSD** | 默认就有，不用改 |
| 公网 IP | **分配公网 IPv4 地址** | 勾选这个选项 |
| 带宽 | **按使用流量**，峰值设 **100Mbps** | 默认选项 |
| 安全组 | 开放端口：**22、80、443** | 默认会开 22，手动加 80 和 443 |
| 登录凭证 | **自定义密码** | 设一个你能记住的密码（8位以上，含大小写+数字） |

3. 点右下角 **「创建实例」**
4. 等 1-2 分钟，服务器就创建好了

**记下来！创建完成后页面上会显示：**

```
公网 IP：xxx.xxx.xxx.xxx（一串数字，比如 123.56.78.90）
```

这个 IP 地址很重要，后面要用。

---

### 2.2 连接到你的服务器

**Windows 电脑：**

1. 按键盘 `Win + R`，输入 `cmd`，回车（会弹出一个黑窗口）
2. 在黑窗口里输入：
   ```
   ssh root@你的服务器IP
   ```
   比如服务器 IP 是 123.56.78.90，就输入：
   ```
   ssh root@123.56.78.90
   ```
3. 回车后会问 "Are you sure you want to continue connecting?" → 输入 `yes`，回车
4. 然后输入你创建服务器时设置的密码（输入密码时屏幕不会显示任何东西，这是正常的，输完直接回车）

**Mac 电脑：**

1. 按键盘 `Cmd + 空格`，搜"终端"，打开终端（Terminal）
2. 输入 `ssh root@你的服务器IP`，回车
3. 同 Windows 的 3-4 步

**登录成功后，你会看到类似这样的提示：**
```
Welcome to Ubuntu 22.04...
root@xxx:~#
```
这说明你已经进入服务器了！

---

### 2.3 在服务器上安装必要软件

登录服务器后，**一条一条**复制粘贴下面的命令（每次粘贴后按回车，等它跑完再粘贴下一条）：

**第 1 条命令：更新系统**
```bash
apt update
```
（等它跑完，大约 30 秒）

**第 2 条命令：安装 Docker**
```bash
curl -fsSL https://get.docker.com | sh
```
（等它跑完，大约 1-2 分钟）

**第 3 条命令：安装 Docker Compose**
```bash
apt install -y docker-compose git
```
（等它跑完，大约 30 秒）

---

### 2.4 拉取项目代码

继续在服务器终端里输入：

```bash
git clone https://github.com/你的用户名/fund-sentiment.git
```

**注意！** 把 `https://github.com/你的用户名/fund-sentiment.git` 换成你实际的 GitHub 仓库地址。

然后进入项目目录：
```bash
cd fund-sentiment
```

---

### 2.5 配置环境变量（最关键的一步）

在服务器终端里输入：
```bash
nano .env
```

这会打开一个文本编辑器。你需要把下面的内容**全部复制粘贴进去**：

```
USE_POSTGRES=true
DATABASE_URL=postgresql+asyncpg://postgres:你的Supabase密码@你的Supabase地址:5432/postgres
USE_REDIS=true
UPSTASH_REDIS_URL=你的Upstash地址
TUSHARE_TOKEN=你的TushareToken
USE_AKSHARE=true
ENVIRONMENT=production
SECRET_KEY=随便打一串乱码比如asdf1234ghjk5678
```

**怎么填？**

| 要填的 | 去哪里找 |
|--------|---------|
| 你的Supabase密码 | 创建 Supabase 项目时你自己设的密码 |
| 你的Supabase地址 | Supabase 控制台 → Settings → Database → Connection string → 复制 URI 里的主机名部分（类似 `db.xxxxx.supabase.co`） |
| 你的Upstash地址 | Upstash 控制台 → 点你的数据库 → 复制 `UPSTASH_REDIS_URL`（以 `redis://` 开头的一长串） |
| 你的TushareToken | tushare.pro → 个人中心 → 接口 Token（如果还没有就删掉这行） |

**填好后怎么保存？**
- 按 `Ctrl + X`
- 按 `Y`
- 按回车

---

### 2.6 启动后端服务

在服务器终端里输入：
```bash
docker-compose -f docker-compose.prod.yml up -d
```

等 1-2 分钟，看到类似 `Creating fund-sentiment-api ... done` 就成功了。

**验证一下：**

在服务器终端输入：
```bash
curl http://localhost:8000/api/v1/health
```

如果返回一串 JSON（带花括号的数据），说明后端启动成功了！

---

## 第三步：部署前端到 Vercel（5 分钟）

### 3.1 打开 Vercel

浏览器访问：https://vercel.com

用你之前注册的账号登录。

### 3.2 导入项目

1. 点击 **「New Project」** 按钮
2. 在列表里找到你的仓库 `fund-sentiment`，点 **「Import」**
3. 出现配置页面后，找到 **「Root Directory」**（根目录），点右边的 **「Edit」**，改成 `frontend`
4. 找到 **「Environment Variables」**（环境变量），添加一条：

   | NAME（名称） | VALUE（值） |
   |-------------|------------|
   | `VITE_API_BASE_URL` | `http://你的服务器IP:8000/api/v1` |

   > 比如你的服务器 IP 是 123.56.78.90，就填 `http://123.56.78.90:8000/api/v1`

5. 点 **「Deploy」** 按钮
6. 等 30 秒到 1 分钟，看到满屏撒花 🎉 就部署成功了

### 3.3 拿到你的网站地址

部署成功后，Vercel 会给你一个网址，类似：
```
fund-sentiment-xxxxx.vercel.app
```

这就是你的网站地址！在浏览器打开它，就能看到基金情绪分析系统了。

---

## 第四步：创建数据库表（2 分钟）

### 4.1 打开 Supabase SQL Editor

1. 浏览器打开 https://supabase.com，登录
2. 点你的项目（fund-sentiment）
3. 左侧菜单找到 **「SQL Editor」**，点击
4. 点 **「New query」**

### 4.2 执行建表语句

你需要把两个 SQL 文件的内容复制粘贴进去。

**第一个文件：建表**

1. 打开 `migrations/001_schema_pg.sql` 这个文件（在项目文件夹里）
2. **全选** 文件内容（Ctrl+A），**复制**（Ctrl+C）
3. 回到 Supabase SQL Editor，**粘贴**（Ctrl+V）
4. 点右下角绿色的 **「Run」** 按钮
5. 看到 "Success" 提示 → 完成

**第二个文件：种子数据**

1. 打开 `migrations/002_seed_data.sql` 这个文件
2. 重复上面 2-5 步

---

## 第五步：验证（3 分钟）

1. 浏览器打开 Vercel 给你的网址
2. 你应该能看到：

   - **顶部**：一条市场快照条（上证、深证、创业板、科创50 的涨跌）
   - **左侧**：导航栏（大盘情绪、基金查询、我的自选、我的持仓、数据复盘）
   - **中间**：多指数情绪仪表盘（四个指数的情绪卡片）
   - **下方**：板块情绪速览 + 机会雷达

3. 点左侧「基金查询」，搜索框输入基金代码试试
4. 点「我的持仓」，看看板块重叠度热力图

**如果页面是空白的**：按 F12 → 点 Console，看看有没有红色报错。截图发给我。

---

## 常见问题

### Q1：打开网站是空白的？

A：检查 Vercel 的环境变量 `VITE_API_BASE_URL` 是否填对了。IP 地址后面要有 `:8000/api/v1`。

### Q2：后端显示「数据库连接失败」？

A：检查 `.env` 里的 `DATABASE_URL` 是否填对了。Supabase 的连接字符串格式是：
```
postgresql+asyncpg://postgres:你的密码@db.xxxxx.supabase.co:5432/postgres
```

### Q3：ECS 服务器突然连不上了？

A：抢占式实例可能会被回收。去阿里云控制台重新创建一个就行，代码和数据都在 GitHub 和 Supabase 上，不会丢。

### Q4：想看到真实数据而不是 Mock 数据？

A：确保 `.env` 里填了 `TUSHARE_TOKEN`，并且 token 有效。

---

## 总时间

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 第一步 | 代码推送到 GitHub | 5 分钟 |
| 第二步 | ECS 部署后端 | 10 分钟 |
| 第三步 | Vercel 部署前端 | 5 分钟 |
| 第四步 | Supabase 建表 | 2 分钟 |
| 第五步 | 验证 | 3 分钟 |
| **合计** | | **25 分钟** |

---

有问题随时问我，不要怕问「蠢问题」——每一步我都可以拆得更细。

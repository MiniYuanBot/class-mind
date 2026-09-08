# 学术分布式算法伪代码风格规范（Event-Driven Algol/Pascal 传统）

## 1. 风格定位

- **范式**：事件驱动状态机（Event-Driven State Machine），用于描述网络协议、交换机/Worker 协同、集合通信（AllReduce）等分布式算法。
- **语法血统**：继承 Algol/Pascal 传统，强调可读性、正确性证明友好，而非可执行性。
- **核心目标**：清晰表达“状态初始化 → 事件触发 → 状态转换 → 网络原语”的完整逻辑。

## 2. 基本语法规则

### 2.1 变量与作用域

- 类型隐式推断，不声明类型关键字。
- **数组/多维表**：用方括号声明维度，逗号分隔下标。
  - 示例：`pool[2, s]`、`seen[2, s, n]`、`count[s]`
- **字段访问**：包/消息字段使用点号 `p.field`。
  - 示例：`p.idx`、`p.wid`、`p.ver`、`p.vector`、`p.off`

### 2.2 赋值与初始化（严格区分）

| 符号 | 含义 | 示例 |
| ------ | ------ | ------ |
| `<-` | **唯一赋值运算符**（左箭头） | `pool[p.idx] <- pool[p.idx] + p.vector` |
| `:= {0}` | **批量初始化**（数组/变量归零） | `pool[s], count[s] := {0}` |
| `=` | **相等比较**（因赋值已被 `<-` 占用） | `if count[p.idx] = 0 then` |

- 初始化块允许多变量并列：`pool[2, s], count[2, s], seen[2, s, n] := {0}`

### 2.3 算术与逻辑运算符

- **乘法**：必须使用中间点 `·`（Unicode U+00B7），禁止使用 `*` 或 `×`。
  - 示例：`k·i`、`p.off + k·s`
- **取模**：`%`
- **逻辑**：关键字形式 `and`、`or`、`not`，不使用 `&&` / `||` / `!`
- **比较**：`=`（等于）、`!=`（不等于）、`<`、`>`、`<=`、`>=`

### 2.4 控制流

- **条件**：`if condition then ... else ...`
  - `then` 和 `else` 为显式关键字，不可省略。
  - 条件为真/假的分支使用缩进，不使用 `begin/end` 或花括号。
- **计数循环**：`for i in start:end do ...`（两端均包含，步长默认为 1）
- **无限/事件循环**：`repeat ... until condition`（至少执行一次）

### 2.5 数组切片与向量操作

- **切片语法**：`U[p.off : p.off+k]`（冒号前后保留空格）
- **向量加法**：隐式逐元素相加，直接使用 `+`。
  - 示例：`pool[p.ver, p.idx] <- pool[p.ver, p.idx] + p.vector`

## 3. 事件驱动结构（核心框架）

算法正文由**状态初始化**和**事件处理器**两部分组成，不允许出现传统 `main()` 入口。

### 3.1 状态初始化块

```text
Initialize State:
  n = number of workers
  pool[s], count[s] := {0}
```

- 顶格书写 `Initialize State:`，后续状态变量缩进对齐。
- 允许使用自然语言描述常量，如 `n = number of workers`。

### 3.2 事件处理器

| 事件类型 | 语法模板 |
| -------- | -------- |
| 接收包 | `upon receive packet p(field1, field2, ...) :` |
| 超时 | `upon timeout p /* Handler Label */ :` |

- **参数列表**：在事件名后用小括号声明包的字段，如 `p(wid, ver, idx, off, vector)`。
- **处理器标签**：超时等处理器可在参数后使用 `/* Comment */` 标注。
- 事件处理内部逻辑统一缩进，分支保持对齐。

## 4. 网络原语（一等操作）

以下关键字直接作为语句使用，不视为函数调用，不加括号：

| 原语 | 语义 | 示例 |
| ------ | ------ | ------ |
| `send p` | 单播发送 | `send p` |
| `multicast p` | 组播/广播聚合结果 | `multicast p` |
| `forward p to dst` | 单播转发给指定目标 | `forward p to p.wid` |
| `drop p` | 丢弃当前包 | `drop p` |
| `recieve p(...)` | 接收事件（事件关键字，非主动调用） | `upon receive p(idx, off, vector)` |

## 5. 状态管理约定

### 5.1 双版本 Ping-Pong（可靠传输）

- 使用二进制版本号 `ver ∈ {0, 1}`，通过 `(p.ver+1)%2` 翻转。
- 状态表按版本维度划分：`pool[2, s]`、`count[2, s]`、`seen[2, s, n]`。

### 5.2 模 n 计数技巧

- 计数器使用 `% n` 递增，**回到 0 表示“刚好收齐”**。

  ```text
  count[p.ver, p.idx] <- (count[p.ver, p.idx] + 1) % n
  if count[p.ver, p.idx] = 0 then
    // 聚合完成
  ```

### 5.3 位图去重

- `seen[ver, idx, wid]` 记录特定 worker 是否已贡献。
- 置位新版本时，**同步清除旧版本位图**，为下一轮做准备：

  ```text
  seen[p.ver, p.idx, p.wid] <- 1
  seen[(p.ver+1)%2, p.idx, p.wid] <- 0
  ```

## 6. 命名约定

| 类别 | 风格 | 示例 |
| ------ | ------ | ------ |
| 状态变量 | 小写全拼，描述性 | `pool`, `count`, `seen`, `timer` |
| 包/消息 | 单字母 `p` 或 `pkt` | `p` |
| 包字段 | 小写缩写 | `idx`, `off`, `ver`, `wid`, `vector` |
| 全局数据/矩阵 | 大写单字母或缩写 | `U`, `A` |
| 常量/参数 | 大写单字母 | `k`（块大小）、`s`（槽位数）、`n`（节点数） |
| 索引变量 | 单字母 | `i`, `j` |

## 7. 注释与排版

- **行尾注释**：使用 `// 注释内容`，用于解释算法意图。
- **处理器标签**：使用 `/* Label */`，如 `/* Timeout Handler */`。
- **缩进**：使用 2 个空格（示例中看似 2 空格或对齐制表位，统一为 2 空格）。
- **空行**：事件处理器之间用空行分隔，提高可读性。

## 8. 完整示例模板

以下模板展示了全部语法与结构规范，生成新算法时应遵循同一模式：

```text
Initialize State:
  n = number of workers
  s = number of slots
  k = chunk size
  pool[2, s], count[2, s], seen[2, s, n] := {0}

upon receive packet p(wid, ver, idx, off, vector):
  if seen[p.ver, p.idx, p.wid] = 0 then
    seen[p.ver, p.idx, p.wid] <- 1
    seen[(p.ver+1)%2, p.idx, p.wid] <- 0
    count[p.ver, p.idx] <- (count[p.ver, p.idx] + 1) % n
    if count[p.ver, p.idx] = 1 then
      pool[p.ver, p.idx] <- p.vector
    else
      pool[p.ver, p.idx] <- pool[p.ver, p.idx] + p.vector
    if count[p.ver, p.idx] = 0 then
      p.vector <- pool[p.ver, p.idx]
      multicast p
    else
      drop p
  else
    if count[p.ver, p.idx] = 0 then
      p.vector <- pool[p.ver, p.idx]
      forward p to p.wid
    else
      drop p

upon timeout p /* Timeout Handler */:
  send p
  start_timer(p)
```

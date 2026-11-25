---
title: 架构总览
description: 整体骨架：进程模型、一条 SQL 的执行流程、存储与 MVCC 怎么摆——以及并发、持久性与扩展怎么接在骨架上。
date: "2026-11-24"
cascade:
  categories:
    - 架构总览
tags:
  - 架构总览
---

# 架构总览

这一阶段回答两件事：**这个内核整体长什么样**，
以及**并发、持久性与扩展怎么接在骨架上**。
第一篇画骨架：进程模型、进程之间的通信、一条 SQL 的执行流程、
存储与 MVCC；第二篇往下拆：三层锁、WAL 的坐标、复制两条路、扩展的几个口子。
不展开单个机制的细节——那些留给后面的阶段。

文章：

- [PostgreSQL 19 整体架构](./postgresql19-architecture.md) —— 第一篇
- [PostgreSQL 19 的并发、持久性与扩展](./postgresql19-concurrency-persistence-extension.md) —— 第二篇

<script setup lang="ts">
// 出包状态：各平台快照的公共子集。
//
// **平台名不写死**——`platform` 那一列是平台 id（从接口面来），
// 界面上不认得它也照样摆。
import type { OutboxSnapshot } from "../api/types";

defineProps<{ snapshots: OutboxSnapshot[] }>();
</script>

<template>
  <section class="publish">
    <h2>出包状态</h2>

    <p v-if="!snapshots.length" data-test="empty">还没有出包快照。</p>

    <table v-else data-test="table">
      <thead>
        <tr>
          <th>平台</th>
          <th>状态</th>
          <th>标题</th>
          <th>更新时间</th>
          <th>地址</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="snapshot in snapshots" :key="`${snapshot.platform}-${snapshot.content_id}`">
          <td>{{ snapshot.platform }}</td>
          <td>{{ snapshot.status }}</td>
          <td>
            {{ snapshot.title }}
            <span v-if="snapshot.reason" class="publish__reason">
              {{ snapshot.reason }}
            </span>
          </td>
          <td>{{ snapshot.updated_at }}</td>
          <td>
            <a v-if="snapshot.published_url" :href="snapshot.published_url">
              {{ snapshot.published_url }}
            </a>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.publish {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-2);
  box-shadow: var(--shadow-1);
  padding: var(--sp-4) var(--sp-5);
}

.publish h2 {
  margin-bottom: var(--sp-3);
  font-size: var(--fs-4);
}

.publish p {
  color: var(--text-3);
  font-size: var(--fs-2);
}

.publish td {
  vertical-align: top;
}

/* 出包失败的原因——跟在标题下面，一眼看得到。 */
.publish__reason {
  display: block;
  margin-top: 2px;
  color: var(--text-3);
  font-size: var(--fs-1);
}
</style>

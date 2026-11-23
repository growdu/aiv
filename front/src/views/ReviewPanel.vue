<script setup lang="ts">
// 统一审校面板：**两条线的信号长得一样，在同一张表里排着**（规格 G3）。
//
// **信号不是门禁**（规格 §7.2 的反面）：顶上的 `gate` 只看审校记录的状态，
// 下面这些信号是给人看的——命中的信号**不影响**能不能过。
import { computed } from "vue";

import type { ReviewReport, Signal } from "../api/types";

const props = defineProps<{
  report: ReviewReport | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  (event: "locate", signal: Signal): void;
}>();

/** 严重程度从重到轻。 */
const SEVERITIES = ["error", "warn", "info"];

/** 排好序的信号：**error → warn → info，同级按 `rule` 字母序**。 */
const signals = computed<Signal[]>(() => {
  const list = props.report?.signals ?? [];
  const rank = (signal: Signal) => {
    const index = SEVERITIES.indexOf(signal.severity);
    return index === -1 ? SEVERITIES.length : index;
  };
  return [...list].sort(
    (a, b) => rank(a) - rank(b) || a.rule.localeCompare(b.rule),
  );
});

const counts = computed(() => props.report?.counts ?? { error: 0, warn: 0, info: 0 });
</script>

<template>
  <section class="review">
    <header class="review__head">
      <h2>审校</h2>
      <p v-if="busy" data-test="busy">正在审校……</p>
    </header>

    <p v-if="!report" data-test="empty">还没有审校结果。</p>

    <template v-else>
      <!-- 门禁状态：只看审校记录的状态，**不是**信号说了算。 -->
      <p
        data-test="gate"
        :class="{ 'review__gate--blocking': report.gate.blocking }"
      >
        {{ report.gate.status }} —— {{ report.gate.reason }}
      </p>

      <p class="review__counts">
        <span data-test="count-error">错误 {{ counts.error }}</span>
        <span data-test="count-warn">警告 {{ counts.warn }}</span>
        <span data-test="count-info">提示 {{ counts.info }}</span>
      </p>

      <p v-for="(note, index) in report.notes" :key="`note-${index}`">
        {{ note }}
      </p>

      <ul class="review__signals">
        <li
          v-for="signal in signals"
          :key="`${signal.rule}-${signal.target}`"
          data-test="signal"
          :data-rule="signal.rule"
          :data-severity="signal.severity"
        >
          <button type="button" @click="emit('locate', signal)">
            <span class="review__severity">{{ signal.severity }}</span>
            <span class="review__rule">{{ signal.rule }}</span>
            <span class="review__target">{{ signal.target }}</span>
          </button>
          <pre class="review__excerpt">{{ signal.excerpt }}</pre>
          <p class="review__detail">{{ signal.detail }}</p>
        </li>
      </ul>
    </template>
  </section>
</template>

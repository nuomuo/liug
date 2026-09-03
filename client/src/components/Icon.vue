<script setup>
// 与原版一致：svg + <use> 引用内联雪碧图
const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 16 },
});
</script>

<template>
  <svg
    class="icon"
    :width="props.size"
    :height="props.size"
    aria-hidden="true"
  >
    <use :xlink:href="'#' + props.name" :href="'#' + props.name"></use>
  </svg>
</template>

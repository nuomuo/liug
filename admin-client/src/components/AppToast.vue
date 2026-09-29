<script setup>
import { toast } from '../toast';
</script>

<template>
  <Teleport to="body">
    <div v-if="toast.show" class="toast" :class="{ error: toast.error }">{{ toast.msg }}</div>
  </Teleport>
</template>

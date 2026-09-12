// @sniptest filename=bp_step_limits.ts
// @sniptest show=1-8
// Simple task (3-5 actions)
let maxSteps = 5;

// Medium complexity (5-15 actions)
maxSteps = 15;

// Complex multi-page task (15-30 actions)
maxSteps = 30;

const results = [maxSteps];
export { results };

const agent = client.Agent({ session });
const result = await agent.run({ task: 'Complete task' });

if (result.success) {
  console.log(result.answer);
} else {
  console.log(`Agent failed: ${result.answer}`);
}

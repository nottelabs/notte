// Example usage of the TypeScript SDK with custom logging

import { NotteClient } from '@notte/sdk';

async function exampleUsage() {
  const client = new NotteClient();

  // Example 1: Using default logging (similar to Python's live_log_step)
  await client.Session().use(async (session) => {
    const agent = client.Agent({ session, max_steps: 5 });

    // This will use the default logger that formats output like Python's live_log_step
    const result = await agent.run({
      task: "Find the best Italian restaurant in SF"
    });

    console.log(`Agent completed with success: ${result.success}`);
    console.log(`Answer: ${result.answer}`);
  });

  // Example 2: Using custom update handler
  await client.Session().use(async (session) => {
    const agent = client.Agent({ session, max_steps: 3 });

    const result = await agent.run({
      task: "Check the weather today", url: "https://www.google.com/search?q=weather"
    });

    console.log(`Final result: ${result.answer}`);
  });

  // Example 3: Non-blocking start with custom handler
  await client.Session().use(async (session) => {
    const agent = client.Agent({ session, max_steps: 10 });

    // Start the agent without waiting
    await agent.start({
      task: "Book a table for 2 at 7pm today"
    });

    console.log(`Agent ${agent.agentId} started, monitoring status...`);

    // You can check status later
    setTimeout(async () => {
      const status = await agent.status();
      console.log('Agent status:', status);
    }, 5000);
  });
}

// Example of the default logger output format:
/*
✨ Step 1 (agent: agent-123)
📝 Current page: Restaurant search page showing Italian options in San Francisco
🔬 Previous goal: ✅ Successfully loaded the search page
🧠 Memory: Found 5 Italian restaurants in SF area
🎯 Next goal: Compare ratings and select the best one
🆔 Relevant ids:
   ▶ restaurant-1: Highly rated authentic Italian place
   ▶ filter-rating: Sort by rating option
⚡ Taking action:
   ▶ ClickAction with id restaurant-1

*/

if (require.main === module) {
  exampleUsage().catch(console.error);
}

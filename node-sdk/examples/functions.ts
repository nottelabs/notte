import { NotteClient } from 'notte-sdk';

// Initialize the client
const client = new NotteClient({
	apiKey: process.env.NOTTE_API_KEY || 'your-api-key-here',
});

async function functionExample() {
	try {
		// Create a function instance with your function ID
		const fn = client.NotteFunction({
			function_id: 'your-function-id',
		});

		console.log('Function ID:', fn.getFunctionId());

		// Logs arrive during execution; await resolves with the final response.
		const result = await fn.run({
			url: 'https://example.com',
		});

		console.log('Function run result:', result);
		console.log('Function run status:', result.status);

		// Get metadata for the function run
		const metadata = await fn.getRun(result.function_run_id);
		console.log('Function run metadata:', metadata);

		// Disable live logs. Standard execution still waits for completion.
		await fn.run({ url: 'https://example.com' }, { stream: false });

		// Optional: obtain a run ID before starting execution.
		const created = await fn.createRun();
		await fn.run({ url: 'https://example.com' }, { functionRunId: created.function_run_id });

	} catch (error) {
		console.error('Error running function:', error);
	}
}

// Run the example
if (require.main === module) {
	functionExample();
}

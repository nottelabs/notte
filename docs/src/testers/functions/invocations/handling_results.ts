// @sniptest filename=handling_results.ts
// @sniptest show=8-22
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

const result = await fn.run({ url: 'https://example.com' });

// Check status
if (result.status === 'closed') {
  console.log('Success!');
  console.log(result.result); // Function return value
} else if (result.status === 'failed') {
  console.log('Function failed');
  console.log(result.result); // Error message
}

// Access metadata
console.log(`Function ID: ${result.function_id}`);
console.log(`Run ID: ${result.function_run_id}`);
console.log(`Session ID: ${result.session_id}`);

export { result };

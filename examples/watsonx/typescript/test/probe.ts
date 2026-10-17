import { runDemo } from '../src/demo.ts';
import { transport } from './transport.ts';

runDemo(transport(process.argv[2], true).mock).then(result => console.log(JSON.stringify(result))).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});

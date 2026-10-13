// @sniptest filename=conditional_actions.ts
// @sniptest show=1-19
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: 'goto', url: 'https://example.com' });

  // Check if element exists
  const result = await session.execute({ type: 'click', selector: 'button.optional' }, { raiseOnFailure: false });

  if (result.success) {
    // Element was there and clicked
    await session.execute({ type: 'click', selector: 'button.next' });
  } else {
    // Element wasn't there, skip
    console.log('Optional button not found, continuing...');
  }
});

const status = await session.status();
const failedClick = status.steps?.find(step => {
  const value = step.value as {
    success?: boolean;
    action?: { type?: string; selector?: { playwright_selector?: string } };
  } | undefined;
  return value?.action?.type === 'click'
    && value.action.selector?.playwright_selector === 'button.optional'
    && value.success === false;
});
if (!failedClick) throw new Error('The missing optional button should return an unsuccessful action');

export { status };

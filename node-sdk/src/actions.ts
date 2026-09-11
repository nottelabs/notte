/**
 * Typed action builders, the counterpart of `notte_sdk.actions` in Python.
 *
 * Every builder returns the exact member of the `ExecuteAction` union that
 * `session.execute()` accepts, with `type` already set:
 *
 * ```ts
 * import { actions } from 'notte-sdk';
 *
 * await session.execute(actions.goto({ url: 'https://www.notte.cc' }));
 * await session.execute(actions.fill({ id: 'I1', value: 'user@example.com' }));
 * await session.execute(actions.goBack());
 * ```
 */
import type { PageExecuteData } from '@/lib/client/types.gen';

/** Discriminated union of every action `session.execute()` accepts. */
export type ExecuteAction = PageExecuteData['body'];

/** The `type` discriminator of an `ExecuteAction`. */
export type ActionType = ExecuteAction['type'];

/** The union member whose `type` is `T`. */
export type ActionOfType<T extends ActionType> = Extract<ExecuteAction, { type: T }>;

/** The fields of an action minus its `type` discriminator. */
export type ActionInput<T extends ActionType> = Omit<ActionOfType<T>, 'type'>;

/** Builders take an optional argument when every field of the action is optional. */
type BuilderArgs<T extends ActionType> = Record<never, never> extends ActionInput<T>
  ? [input?: ActionInput<T>]
  : [input: ActionInput<T>];

function builder<T extends ActionType>(type: T): (...args: BuilderArgs<T>) => ActionOfType<T> {
  return (...[input]: BuilderArgs<T>): ActionOfType<T> => ({ ...(input ?? {}), type }) as ActionOfType<T>;
}

// Browser actions
export const goto = builder('goto');
export const gotoNewTab = builder('goto_new_tab');
export const closeTab = builder('close_tab');
export const switchTab = builder('switch_tab');
export const goBack = builder('go_back');
export const goForward = builder('go_forward');
export const reload = builder('reload');
export const wait = builder('wait');
export const pressKey = builder('press_key');
export const scrollUp = builder('scroll_up');
export const scrollDown = builder('scroll_down');
export const captchaSolve = builder('captcha_solve');
export const help = builder('help');
export const completion = builder('completion');
export const scrape = builder('scrape');
export const emailRead = builder('email_read');
export const emailVerificationRead = builder('email_verification_read');
export const smsRead = builder('sms_read');
export const evaluateJs = builder('evaluate_js');
export const formFill = builder('form_fill');

// Interaction actions (need an element `id` from `observe()` or a `selector`)
export const click = builder('click');
export const fill = builder('fill');
export const multiFactorFill = builder('multi_factor_fill');
export const fallbackFill = builder('fallback_fill');
export const check = builder('check');
export const selectDropdownOption = builder('select_dropdown_option');
export const uploadFile = builder('upload_file');
export const downloadFile = builder('download_file');

/** Namespace object mirroring `from notte_sdk import actions`. */
export const actions = {
  goto,
  gotoNewTab,
  closeTab,
  switchTab,
  goBack,
  goForward,
  reload,
  wait,
  pressKey,
  scrollUp,
  scrollDown,
  captchaSolve,
  help,
  completion,
  scrape,
  emailRead,
  emailVerificationRead,
  smsRead,
  evaluateJs,
  formFill,
  click,
  fill,
  multiFactorFill,
  fallbackFill,
  check,
  selectDropdownOption,
  uploadFile,
  downloadFile,
} as const;

/** True when the action is a captcha solve, which gets a longer request timeout and 408 retries. */
export function isCaptchaSolveAction(action: ExecuteAction): action is ActionOfType<'captcha_solve'> {
  return action.type === 'captcha_solve';
}

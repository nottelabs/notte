import { describe, it, expect, expectTypeOf } from 'vitest';
import * as builders from '@/actions';
import { actions, isCaptchaSolveAction, type ActionOfType, type ExecuteAction } from '@/actions';

const EXPECTED_BUILDERS = [
  'click', 'fill', 'goto', 'gotoNewTab', 'closeTab', 'switchTab', 'goBack', 'goForward', 'reload', 'wait',
  'pressKey', 'scrollUp', 'scrollDown', 'check', 'selectDropdownOption', 'uploadFile', 'downloadFile', 'formFill',
  'multiFactorFill', 'fallbackFill', 'captchaSolve', 'emailRead', 'emailVerificationRead', 'smsRead', 'evaluateJs',
  'scrape', 'help', 'completion',
] as const;

describe('actions', () => {
  it('exposes the same 28 builders as notte_sdk.actions, as a namespace and individually', () => {
    expect(Object.keys(actions).sort()).toEqual([...EXPECTED_BUILDERS].sort());
    for (const name of EXPECTED_BUILDERS) {
      expect(builders[name]).toBe(actions[name]);
    }
  });

  it('sets the type discriminator and keeps the fields', () => {
    expect(actions.click({ id: 'B1' })).toEqual({ type: 'click', id: 'B1' });
    expect(actions.fill({ selector: 'input', value: 'x', clear_before_fill: true })).toEqual({
      type: 'fill', selector: 'input', value: 'x', clear_before_fill: true,
    });
    expect(actions.goto({ url: 'https://example.com' })).toEqual({ type: 'goto', url: 'https://example.com' });
    expect(actions.wait({ time_ms: 500 })).toEqual({ type: 'wait', time_ms: 500 });
    expect(actions.evaluateJs({ code: '1' })).toEqual({ type: 'evaluate_js', code: '1' });
    expect(actions.formFill({ value: { email: 'a@b.c' } })).toEqual({ type: 'form_fill', value: { email: 'a@b.c' } });
    expect(actions.captchaSolve({ captcha_type: 'hcaptcha' })).toEqual({ type: 'captcha_solve', captcha_type: 'hcaptcha' });
  });

  it('accepts no argument when every field is optional', () => {
    expect(actions.goBack()).toEqual({ type: 'go_back' });
    expect(actions.goForward()).toEqual({ type: 'go_forward' });
    expect(actions.reload()).toEqual({ type: 'reload' });
    expect(actions.captchaSolve()).toEqual({ type: 'captcha_solve' });
    expect(actions.scrollDown()).toEqual({ type: 'scroll_down' });
    expect(actions.help({ reason: 'stuck' })).toEqual({ type: 'help', reason: 'stuck' });
  });

  it('does not let the input override the type', () => {
    const input = { type: 'goto', url: 'https://example.com' } as unknown as Parameters<typeof actions.click>[0];
    expect(actions.click(input).type).toBe('click');
  });

  it('identifies captcha solve actions', () => {
    expect(isCaptchaSolveAction(actions.captchaSolve())).toBe(true);
    expect(isCaptchaSolveAction(actions.goBack())).toBe(false);
  });

  it('is typed against the generated execute body', () => {
    expectTypeOf(actions.goto({ url: 'x' })).toEqualTypeOf<ActionOfType<'goto'>>();
    expectTypeOf(actions.goto({ url: 'x' })).toMatchTypeOf<ExecuteAction>();
    expectTypeOf(actions.click({ id: 'B1' })).toMatchTypeOf<ExecuteAction>();
    expectTypeOf(actions.goBack()).toMatchTypeOf<ExecuteAction>();
    expectTypeOf<ActionOfType<'fill'>['type']>().toEqualTypeOf<'fill'>();
    // @ts-expect-error a goto action needs a url
    void actions.goto({});
    // @ts-expect-error a wait action needs time_ms
    void actions.wait();
    // @ts-expect-error unknown fields are rejected
    void actions.click({ id: 'B1', foo: 1 });
  });
});

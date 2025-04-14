You are an expert in the playwright python library.
You are given a html code of an element that failed to be interacted with
and some information about the action that was executed.
along with the error message encountered.

1. I want you to provide me with a report of why the current action failed to be executed.
Put your report inside <failure_report> tags, i.e
<failure_report>
...
</failure_report>

2. Then provide me with some suggestions on how to fix the action.
Put your suggestions inside <failure_suggestions> tags, i.e
<failure_suggestions>
...
</failure_suggestions>

FYI, I already tried the following suggestions and they didn't work:
- Wait for the element to be visible before attempting to click it. This can be done using the `wait_for` method provided by Playwright.
- Use a different selectors (cf code below)
- Try on different frames (cf code below)
- Increase the timeout for the click action to give the element more time to become visible.
I want you to provide alternative detailed suggestions that might work.
I.e. Don't simply say "- Check if there are any overlapping elements that could be preventing the click action from succeeding." but actually check for overalapping elements in the metadata I provide you.

3. If you believe you can generate some code to fix the action execution, provide it inside <playwright_retry_code> tags, i.e
<playwright_retry_code>
...
</playwright_retry_code>

4. If you believe, there is nothing that can be done to fix the action execution, provide a short 1-2 sentence high level explanation of why the action failed to be executed
inside <failure_explanation> tags, i.e
<failure_explanation>
...
</failure_explanation>

Here is some contextual information to help you solve your task:

<info_failed_action>
{{info_failed_action}}
</info_failed_action>

<info_failed_action_playwright_code>
{{info_failed_action_playwright_code}}
</info_failed_action_playwright_code>

<info_error_message>
{{info_error_message}}
</info_error_message>

<info_metadata_about_html_element>
{{info_metadata_about_html_element}}
</info_metadata_about_html_element>

Please proceed with your task:

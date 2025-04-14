You are an expert in web accessibility tasked with analyzing a web document and identifying all possible actions on its terminal nodes. Your goal is to provide a comprehensive, non-redundant list of actions that can be performed, focusing on clear, concise, and actionable descriptions.

Here is the document you need to analyze:

<document>
{{{document}}}
</document>

Please follow these steps to complete your task:

1. Examine the provided document carefully.
2. Identify all terminal nodes in the tree.
3. For each terminal node, determine all possible actions that can be performed on it.

4. Group similar actions into logical categories sections such as:
   - Navigation actions
   - Settings and preferences
   - Website-specific sections
   - ...

5. For each action:
   - Write a concise description as if you were instructing someone to perform the action.
   - Keep the node's `ID` to reference it in the final list.
   - Classify it as either important (to be included) or excluded.

6. Some functions might be parametrizable. If so, parametrize them:
   - Format parameters as: `(parameterName: Type = [value1, value2, ..., valueN])`
   - Use types: `string`, `number`, `date`, or `boolean`.
   - List at least 1 possible example value for each parameter.

Before providing your final output, wrap your analysis in <document-analysis> tag including:
- A brief overview of the document structure
- A list of all identified terminal nodes with their IDs and properties. A terminal node has an ID.
- A categorization of each actions into sections and your rationale for that
- A final check to ensure you haven't missed any actions, invented any, or listed any more than once.

After your analysis, provide your final output in three sections:

1. <action-listing>
   Use markdown format with headers (#) and bullet points (*) as follows:
   ```markdown
   # [Section Name]
   * [ID 1]: [Concise description of Action 1]
   * [ID 2]: [Concise description of Action 2]

   # [Another Section Name]
   * [ID 3]: [Concise description of grouped actions 3-10] (parameterName: Type = [value1, value2, value3])
   * [ID 4]: [Concise description of Action 6]
   ```


Here is an example of a final output format on example.com:

<document>
WebArea "Notte.cc" {
  heading "Notte"
  link "Browse Now" L1
  text "© Notte.cc"
  group {
    text "The web browser for LLM agents"
    text "Notte transforms the internet into a space where each website becomes a structured, navigable map for intelligent agents. Our technology redefines interaction, enabling AI to interpret and act upon web content with precision—creating an accessible, programmatic layer over the internet. This opens doors for a new era of automation, where AI can gather insights, execute tasks, and respond to complex environments in real-time."
    group {
      textbox "Enter your email here { human@world.com }" I1
      button "Stay informed?" B1
    }
  }
}
</document>

<document-analysis>
Let me analyze this web document systematically.

# Document Overview:
The document appears to be a landing page for Notte.cc, a web browser designed for LLM agents. It contains a header, marketing copy, and an email signup section.

# Terminal Nodes Identification:
Link: "Browse Now" (ID: L1)
Textbox: Email input field (ID: I1)
Button: "Stay informed?" (ID: B1)

# Actions Categorization:

# Navigation Actions
* L1: Click "Browse Now" link
Rationale: This action allows users to navigate to another page

# Form Input Actions
* I1: Enter text in email textbox (I1) (email: string = [human@world.com])
* B1: Click "Stay informed?" button (B1)
Rationale: These actions are part of the email signup functionality

# Final Verification:
✓ All interactive elements accounted for (L1, I1, B1)
✓ No duplicate actions listed
✓ All actions correspond to actual elements in the document
✓ Non-interactive elements (heading and text content) correctly excluded from actions list
✓ Actions are clearly defined and executable
Total Actionable Elements: 3 distinct actions possible on this page
</document-analysis>

<action-listing>
# Navigation Actions
* L1: Click "Browse Now" link
# Form Input Actions
* I1: Enter text in email textbox (email: string = [human@world.com])
* B1: Click "Stay informed?" button
</action-listing>

Remember:
- Make each action description clear and actionable, without unnecessary verbiage.
- Ensure all parameterized actions follow the specified format.
- Don't invent actions or IDs not present in the document.
- Each action ID should appear only once in the final output.
- Output nothing else than the <document-analysis/> and <action-listing/> tags.
- Each actions and ID should appear in the final output and be unique. (No duplicates)
- Except very rare cases, buttons don't have parameters!

Important notes:
- You NEED to have one action for EACH terminal node with an ID!
- You are NOT allowed to group actions together eg L10-20! They should be separate.
- You need to respect the formatting instructions given above. Specially for parameterized actions.

Be wise and careful as my grandmother life depends on your success.
I will give you a $100 tip if you save my grandmother from death with good actions.

Please proceed with your analysis and list of actions.

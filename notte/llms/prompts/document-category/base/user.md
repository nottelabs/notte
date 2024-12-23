Based on a textual description of a webpage, I want to classifiy the page in one of the following categories:
- “manage-cookies”: manage cookies page, i.e accept/reject cookies, usually in a modal / dialog that ask for user action
- “auth”: sign-in, sign-up pages (also valid if there is a modal that asks you to sign up to continue using the website)
- "homepage": the homepage of the website
- "search-results": multiple item displayed which are a results of a previous search query
- “data-feed”: data display in a grid/sequence such as blog posts, news articles, social media feeds (instagram, linked-in, etc.)
- "item": information page about one particular item, usually displayed after clicking on a link in a previous "search-result" or "data-feed" webpage. This is relevant for product pages on shopping websites, a news/blog article, social media post, a recipe etc. This is mainly a data display page.
- "captcha": CAPTCHA page that ask the user to resolve a captcha before continuing
- "payment": payment page where users need to input their credit-card / delivery information
- “form”: asks for user input of some sorts, form, modal, etc. also valid for contact forms (not auth though since this is already covered by the "auth" category)

if the page is not one of these categories use : "other"

If you are hesitate between 2 categories because you think it's both : return both categories.

Here are some examples:

```
Webpage information:
- URL: https://www.allrecipes.com/search?q=vegetarian+lasagna
- Title: [vegetarian lasagna] Results from Allrecipes
- Description: This is the Allrecipes website's search results page with the query "vegetarian lasagna". Users can search for specific recipes, browse through the search results, navigate to different sections of the website, and access various links related to recipes, meals, and kitchen tips. The page also provides links to social media, editorial process, privacy policy, and other related information.
```
should result in <document-category>search-results</document-category>


```
Webpage information:
- URL: https://www.allrecipes.com/
- Title: Allrecipes | Recipes, How-Tos, Videos and More
- Description: This web page is the cookie consent modal for Allrecipes, focused on user interactions with personalized advertising and data processing. Users can manage their choices for personalized advertising and content by clicking on various buttons or accessing the privacy policy page.
```
should result in <document-category>"manage-cookies"</document-category>


```
Webpage information:
- URL: https://www.allrecipes.com/
- Title: Allrecipes | Recipes, How-Tos, Videos and More
- Description: This is the Allrecipes website interface, focused on providing various recipes and cooking-related content. Users can explore different types of recipes, save their favorite recipes, and visit various social media pages. The interface is organized into different sections, including a main content area, a footer with navigation links, and a section for saving recipes.
```
should result in <document-category>"other"</document-category>


```
Webpage information:
- URL: https://www.allrecipes.com/recipe/278027/worlds-best-now-vegetarian-lasagna/
- Title: World's Best (Now Vegetarian!) Lasagna Recipe
- Description: This is a recipe page for a vegetarian lasagna on Allrecipes.com. The main content displays a detailed recipe including ingredients, directions, nutrition facts, and cooking times. Users can interact with the recipe through various actions like saving, rating, printing, adjusting serving sizes, and viewing related recipes.
```

should result in <document-category>"item"</document-category>

Here is the document I want you to analyse:

<document> {{document}} </document>

Please return the category inside <document-category> tags.

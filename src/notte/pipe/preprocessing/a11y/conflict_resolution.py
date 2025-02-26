import copy
import re

from loguru import logger
from patchright.async_api import Locator, Page

from notte.browser.dom_tree import A11yNode, NodeSelectors
from notte.browser.node_type import NodeCategory
from notte.errors.processing import SnapshotProcessingError
from notte.errors.resolution import ConflictResolutionCheckError
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    find_node_path_by_id,
    list_interactive_nodes,
)


async def resolve_link_conflict(
    page: Page,
    node: A11yNode,
    node_path: list[A11yNode],  # type: ignore[unused-argument]
    locators: list[Locator],
) -> Locator | None:
    if node["role"] != "link":
        return None

    # for links, check that all hrefs are the same
    def remove_http(href: str) -> str:
        return href.replace("http://", "").replace("https://", "")

    base_url = remove_http(page.url).split("/")[0]
    hrefs: list[str | None] = [await locator.get_attribute("href") for locator in locators]
    clean_hrefs: list[str] = [
        remove_http(href).replace(base_url, "").replace("#", "") for href in hrefs if href is not None
    ]

    if len(set(clean_hrefs)) == 1:
        return locators[0]
    else:
        logger.warning(f"{len(locators)} locators found for link '{node['name']}': {clean_hrefs}")
        return None


def list_all_text_names_in_subtree(node: A11yNode) -> list[str]:
    role = node["role"]
    if role in NodeCategory.INTERACTION.roles():
        return []
    if role in ["text", "heading", "paragraph"]:
        return [node["name"]] if node.get("name") else []
    return [name for child in node.get("children", []) for name in list_all_text_names_in_subtree(child)]


def get_first_parent_with_text_elements(
    node: A11yNode,
    path: list[A11yNode],
    depth: int = 1,
    min_depth: int = 1,
    min_nb_text_names: int = 0,
) -> tuple[int | None, list[str]]:
    text_names = list_all_text_names_in_subtree(node)
    if len(text_names) > min_nb_text_names and depth > min_depth:
        return depth, text_names
    if len(path) <= depth:
        return None, []
    new_depth = depth + 1
    return get_first_parent_with_text_elements(
        path[-new_depth],
        path,
        new_depth,
        min_depth=min_depth,
        # TODO: disable this for now, seems to create long recursion
        # min_nb_text_names=min_nb_text_names
    )


async def resolve_conflict_by_text_parents(
    page: Page,
    node: A11yNode,
    node_path: list[A11yNode],
    locators: list[Locator],
    min_depth: int = 1,
    min_nb_text_names: int = 0,
) -> Locator | None:
    depth, text_names = get_first_parent_with_text_elements(
        node, node_path, min_depth=min_depth, min_nb_text_names=min_nb_text_names
    )
    if depth is None:
        # the text names are not found in the subtree
        # and the full path has been exhausted
        return None
    # phase 1: find all locators that match the text names
    candidate_locators: list[Locator] = []
    for candidate_locator in locators:
        for _ in range(depth):
            candidate_locator = candidate_locator.locator("xpath=..")
        for text_name in text_names:
            candidate_locator = candidate_locator.filter(has_text=text_name)

        if await candidate_locator.count() > 0:
            candidate_locators.append(candidate_locator)
    # phase 2: check that all the candidate locators are unique
    if len(candidate_locators) == 0:
        logger.error(
            f"[CONFLICT TEXT RESOLUTION] No candidate locators found for node {node['name']} with role {node['role']}"
        )
        return None
    if len(candidate_locators) > 1:
        logger.warning(
            f"[CONFLICT TEXT RESOLUTION] Multiple candidate locators found: try with increased depth : {depth}"
        )
        # try with increased depth
        return await resolve_conflict_by_text_parents(
            page,
            node,
            node_path,
            locators,
            min_depth=depth,
            min_nb_text_names=len(text_names),
        )
    chosen_locator = candidate_locators[0]
    if await chosen_locator.count() > 1:
        logger.error(
            (
                "[CONFLICT TEXT RESOLUTION] Multiple chosen locators found for "
                f"node {node['name']} with role {node['role']}"
            )
        )
        return None
    # now we have a single candidate locator
    chosen_locators = await chosen_locator.get_by_role(
        role=node["role"],  # type: ignore
        name=node["name"],
        exact=True,
    ).all()
    if len(chosen_locators) != 1:
        raise SnapshotProcessingError(
            dev_message=(
                f"Expected 1 locator, got {len(chosen_locators)} "
                f"with role '{node['role']}' and name '{node['name']}' "
                f"(for depth {depth} and text names {text_names})"
            ),
            url=page.url,
        )
    return chosen_locators[0]


async def resolve_conflicts_in_path(
    page: Page, node: A11yNode, node_path: list[A11yNode], locators: list[Locator], verbose: bool = False
) -> Locator | None:
    # we can go up the path and try to find a more specific locator, one node at a time
    if verbose:
        logger.info(
            f"""
------------------------------------------------------------------
Trying to resolve conflict by going up the path for node (ID = {node.get("id")})
name: '{node["name"]}' role: '{node["role"]}' and len({len(node_path)})
"""
        )
    full_node_path: list[A11yNode] = copy.deepcopy(node_path)
    full_node_path.append(node)
    if node_path[0]["role"] != "WebArea":
        raise ConflictResolutionCheckError(f"the root node should be a WebArea but is '{node_path[0]['role']}'")
    if len(full_node_path) < 2:
        raise ConflictResolutionCheckError("there should be at least two nodes in the path")
    for i in range(1, len(full_node_path) - 1):
        selected_nodes: list[A11yNode] = full_node_path[-i - 1 :]  # noqa: E203
        locator = None
        for _node in selected_nodes:
            base = page if locator is None else locator
            locator = base.get_by_role(role=_node["role"], name=_node["name"], exact=True)  # type: ignore
        if locator is None:
            continue
        locators = await locator.all()
        if len(locators) == 1:
            return locators[0]

    if len(locators) > 1:
        logger.error(
            (
                "[CONFLICT PATH RESOLUTION] Multiple locators found for "
                f"path {node_path[-1]['name']} with role {node_path[0]['role']}"
            )
        )
        return None
    if len(locators) == 0:
        logger.error(
            (
                "[CONFLICT PATH RESOLUTION] No locators found for "
                f"path {node_path[-1]['name']} with role {node_path[0]['role']}"
            )
        )
        return None
    return locators[0]


async def resolve_conflicts_for_nested_buttons(
    page: Page,  # type: ignore[unused-argument]
    node: A11yNode,
    node_path: list[A11yNode],  # type: ignore[unused-argument]
    locators: list[Locator],
) -> Locator | None:
    children = node.get("children", [])
    if node["role"] != "button" or len(children) == 0:
        return None

    # if the conflicts are only on its children, we can resolve them
    # by selecting the parent button
    def nb_conflicting_children(n: A11yNode) -> int:
        nb_conflicting = sum([nb_conflicting_children(child) for child in n.get("children", [])])

        if n["role"] == "button" and n["name"] == node["name"]:
            nb_conflicting += 1
        return nb_conflicting

    nb_conflicting = nb_conflicting_children(node)
    if nb_conflicting == len(locators):
        logger.info(
            f"[CONFLICT NESTED BUTTON RESOLUTION] Found {nb_conflicting} conflicting locators for {node['name']}"
        )
        return locators[0]
    return None


def extract_selector_from_locator(locator: Locator) -> str:
    if "selector='" in str(locator.first):
        part = str(locator.first).split("selector='")[1]
        if "'>" in part:
            part = part.split("'>")[0]
            return part

    match = re.search(r"selector='([^']+)'", str(locator.first))
    if match:
        # return html.unescape(match.group(1))
        raise ValueError(f"Invalid selector: {match.group(1)}")
    return ""


def format_path_for_conflict_resolution(node_path: list[A11yNode] | None) -> tuple[A11yNode, list[A11yNode]]:
    if node_path is None:
        raise ConflictResolutionCheckError("Node path is None")
    if len(node_path) < 2:
        raise ConflictResolutionCheckError("Node path should have at least two nodes")
    node = node_path[0]
    node_path = node_path[1:][::-1]
    if node_path[0]["role"] != "WebArea":
        raise ConflictResolutionCheckError("The first node in the node path should be the root node")
    return node, node_path


async def get_locator_for_node_id(
    page: Page, tree: A11yNode, node_id: str, conflict_resolution: bool = True
) -> Locator | None:
    node_path = find_node_path_by_id(tree, node_id)
    node, node_path = format_path_for_conflict_resolution(node_path)
    if node.get("id") != node_id:
        raise ConflictResolutionCheckError(f"Node with notte_id {node_id} not found in raw accessibility tree")
    return await get_locator_for_a11y_path(page, node, node_path, conflict_resolution)


async def get_locator_for_a11y_path(
    page: Page, node: A11yNode, node_path: list[A11yNode], conflict_resolution: bool = True
) -> Locator | None:
    # Base locator strategy depends on the role and name
    locator = None
    args = {}
    selected, checked = node.get("selected"), node.get("checked")
    if selected:
        args["selected"] = True
    if checked:
        args["checked"] = True

    if node.get("role"):
        if node["role"] in NodeCategory.TEXT.roles() or node["role"] in NodeCategory.IMAGE.roles():
            # no need to get a locator for images or text
            return None
        # Primary strategy: use role and name
        locator = page.get_by_role(role=node["role"], name=node["name"], **args)  # type: ignore
    elif node.get("name"):
        # Fallback: use text content
        locator = page.get_by_text(node["name"], exact=True)

    # VALIDATE THAT THE LOCATOR IS UNIQUE
    if locator is None:
        return None
    locators = await locator.all()
    if len(locators) == 0:
        logger.warning(
            f"Warning: No locators found for '{node['name']}' with role '{node['role']}' trying to relax selector"
        )
        # last resort: try to relax the selector
        locators = await try_relax_selector(page, node)
        if len(locators) == 0:
            logger.error(f"Relaxation failed for node '{node['name']}'")
            return None
        if len(locators) == 1:
            return locators[0]
        logger.warning(f"Multiple locators found for node '{node['name']}' after relaxation (try resolution)")

    elif len(locators) == 1:
        return locators[0]

    if not conflict_resolution:
        logger.error(
            (
                f"[CONFLICT RESOLUTION] Multiple locators found for node with ID {node.get('id')}"
                " but conflict resolution is disabled"
            )
        )
        return None

    conflict_resolvers = [
        resolve_link_conflict,
        resolve_conflicts_in_path,
        resolve_conflicts_for_nested_buttons,
        resolve_conflicts_by_order,
        resolve_conflict_by_text_parents,
    ]
    for resolver in conflict_resolvers:
        out_locator = await resolver(page, node, node_path, locators)
        if out_locator is not None:
            return out_locator
    return None


css_path_code = """(el) => {
    if (!el || !(el instanceof Element)) return '';
    var path = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
        let selector = el.nodeName.toLowerCase();
        if (el.id) {
            selector += '#' + el.id;
            path.unshift(selector);
            break;
        } else {
            let sib = el, nth = 1;
            while (sib.previousElementSibling) {
                sib = sib.previousElementSibling;
                if (sib.nodeName.toLowerCase() === selector) nth++;
            }
            if (nth !== 1) selector += ":nth-of-type("+nth+")";
        }
        path.unshift(selector);
        el = el.parentElement;
    }
    return path.join(' > ');
}
"""

xpath_code = """(element) => {
    function getPathTo(element) {
        if (!element) {
            return null;
        }
        if (element.id && element.id !== '')
            return `//*[@id="${element.id}"]`;

        if (element === document.body)
            return '/html/body';

        let ix = 0;
        let siblings = element.parentNode.childNodes;

        for (let sibling of siblings) {
            if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                ix++;
            if (sibling === element) {
                const num = getPathTo(element.parentNode);
                return `${num}/${element.tagName.toLowerCase()}[${ix}]`;
            }
        }
}
    return getPathTo(element);
}"""


async def get_html_selector(locator: Locator) -> NodeSelectors | None:
    """
    Convert a Playwright locator to its XPath representation,
    prioritizing IDs and full element paths.

    Args:
        locator: Playwright Locator object

    Returns:
        str: XPath expression
    """
    try:
        # First, try to get the element using the locator
        element = await locator.element_handle()
        if not element:
            return None

        # Evaluate JavaScript to get the full path
        xpath: str = await locator.page.evaluate(
            xpath_code,
            element,
        )
        css_path: str = await locator.evaluate(css_path_code)

        playwright_selector: str = extract_selector_from_locator(locator)
        return NodeSelectors(
            playwright_selector=playwright_selector,
            css_selector=css_path,
            xpath_selector=xpath,
            notte_selector="",
            in_iframe=False,
            in_shadow_root=False,
            iframe_parent_css_selectors=[],
        )

    except Exception:
        # Fallback to basic selector parsing if the above fails
        selector: str = extract_selector_from_locator(locator)

        def return_selector(selector: str) -> NodeSelectors:
            return NodeSelectors(
                playwright_selector=selector,
                css_selector="",
                xpath_selector="",
                notte_selector="",
                in_iframe=False,
                in_shadow_root=False,
                iframe_parent_css_selectors=[],
            )

        # Handle existing XPath
        if selector.startswith("xpath="):
            return return_selector(selector.replace("xpath=", ""))

        # Handle ID-based selectors
        id_match = re.search(r"#([^[:space:]]+)", selector)
        if id_match:
            return return_selector(f'//*[@id="{id_match.group(1)}"]')

        # Handle tag-based selectors (e.g., "div >> nth=0")
        tag_match = re.match(r"^([a-zA-Z0-9]+)", selector)
        if tag_match:
            tag = tag_match.group(1)
            # If there's an nth selector
            nth_match = re.search(r"nth=(\d+)", selector)
            if nth_match:
                position = int(nth_match.group(1)) + 1  # nth is 0-based, XPath is 1-based
                return return_selector(f"//{tag}[{position}]")
            return return_selector(f"//{tag}")

        # Default case
        return return_selector(selector)


# ####################################################################
# ######################### TODO #####################################
# ####################################################################


async def resolve_conflicts_by_order(
    page: Page,  # type: ignore[unused-argument]
    node: A11yNode,
    node_path: list[A11yNode],
    locators: list[Locator],
) -> Locator | None:
    # heuristic
    # if there as as many locators as paths
    # then the ordering should be the same as the path
    check_node = node_path[0]
    all_paths = find_all_paths_by_role_and_name(node, check_node["role"], check_node["name"])
    if len(all_paths) != len(locators):
        return locators[0]
    for path, locator in zip(all_paths, locators):
        if path[0] == check_node:
            return locator
    raise ConflictResolutionCheckError(
        f"no matching locator found for node(role='{check_node['role']}', name='{check_node['name']}')"
    )


async def resolve_conflict_with_closest_neighbor(page: Page, tree: A11yNode, node_id: str) -> Locator | None:
    async def find_neighbors_with_valid_locators() -> tuple[Locator | None, Locator | None]:
        interactive_nodes_ids = [n.get("id", "no_id") for n in list_interactive_nodes(tree, only_with_id=True)]
        node_index = interactive_nodes_ids.index(node_id)

        async def get_valid_locator(index: int, step: int = 1) -> Locator | None:
            if index < 0 or index >= len(interactive_nodes_ids):
                return None

            locator = await get_locator_for_node_id(
                page=page,
                tree=tree,
                node_id=interactive_nodes_ids[index],
                conflict_resolution=False,
            )
            if locator is None:
                return await get_valid_locator(index + step, step)
            logger.info(f"Found locator for idx: {index} with id: {interactive_nodes_ids[index]}")
            return locator

        left_locator = await get_valid_locator(node_index - 1, -1)
        right_locator = await get_valid_locator(node_index + 1, 1)

        return left_locator, right_locator

    async def find_common_ancestor(locator1: Locator, locator2: Locator) -> Locator | None:
        # JavaScript function to find common ancestor
        js_code = """(elements) => {
            const [el1, el2] = elements;
            if (!el1 || !el2) return null;

            const parents1 = [el1];
            let parent = el1.parentElement;
            while (parent) {
                parents1.push(parent);
                parent = parent.parentElement;
            }

            parent = el2;
            while (parent) {
                if (parents1.includes(parent)) {
                    return parent;
                }
                parent = parent.parentElement;
            }

            return null;
        }"""

        # Get the actual DOM elements
        element1 = await locator1.element_handle()
        element2 = await locator2.element_handle()

        # Find common ancestor using JavaScript
        ancestor = await page.evaluate(js_code, [element1, element2])

        # Clean up the element handles
        await element1.dispose()
        await element2.dispose()

        return page.locator("*").nth(0) if ancestor else None

    left_locator, right_locator = await find_neighbors_with_valid_locators()
    if left_locator is None or right_locator is None:
        return None
    ancestor = await find_common_ancestor(left_locator, right_locator)
    if ancestor is None:
        return None
    node_path = find_node_path_by_id(tree, node_id)
    if node_path is None:
        raise ConflictResolutionCheckError("Node path not found")
    name, role = node_path[0]["name"], node_path[0]["role"]
    original_locator = page.get_by_role(role=role, name=name, exact=True)  # type: ignore
    return ancestor.filter(has=original_locator).first


async def try_relax_selector(page: Page, node: A11yNode, relax_level: int = 1) -> list[Locator]:
    if relax_level > 4:
        return []
    locator = page.get_by_role(
        role=node["role"],  # type: ignore[type-assignment]
    )
    patterns = node["name"].split(" ")
    for pattern in patterns:
        pattern = pattern.strip()
        if (
            len(pattern) == 0
            or (relax_level > 1 and pattern.isdigit())
            or (relax_level > 2 and not pattern.isalpha())
            or (relax_level > 3 and len(pattern) <= 2)
        ):
            continue
        locator = locator.filter(has_text=pattern)

    locators = await locator.all()
    if len(locators) == 0:
        return await try_relax_selector(page, node, relax_level + 1)
    return locators

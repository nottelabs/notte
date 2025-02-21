from dataclasses import dataclass

from notte.browser.dom_tree import A11yNode, A11yTree
from notte.errors.processing import (
    InvalidA11yTreeType,
    NodeFilteringResultsInEmptyGraph,
)
from notte.pipe.preprocessing.a11y.id_generation import (
    generate_sequential_ids,
    sync_ids_between_trees,
    sync_image_ids_between_trees,
)
from notte.pipe.preprocessing.a11y.pruning import (
    PruningConfig,
    complex_processing_accessiblity_tree,
    prune_non_dialogs_if_present,
    simple_processing_accessiblity_tree,
)

# TODO: enable this if needed
# from notte.pipe.preprocessing.a11y.text import prune_text_nodes
from notte.pipe.preprocessing.a11y.traversal import (
    find_all_paths_by_role_and_name,
    find_node_path_by_id,
    list_interactive_nodes,
)
from notte.pipe.preprocessing.a11y.validation import (
    check_interactions_consistency_accross_ax_trees,
)
from notte.pipe.preprocessing.a11y.viz import visualize_a11y_tree


@dataclass
class ProcessedA11yTree:
    processed_tree: A11yNode
    raw_tree: A11yNode
    # simple is used to feed to the LLMS (reduced size tree)
    simple_tree: A11yNode
    _filtered: bool = False

    def __post_init__(self):
        if not self._filtered:
            _ = check_interactions_consistency_accross_ax_trees(self.simple_tree, self.raw_tree, only_with_id=True)

    @staticmethod
    def from_a11y_tree(tree: A11yTree, config: PruningConfig) -> "ProcessedA11yTree":
        simple_tree = simple_processing_accessiblity_tree(tree.simple, config)
        if simple_tree is None:
            raise NodeFilteringResultsInEmptyGraph("pruning simple tree")
        simple_tree = generate_sequential_ids(simple_tree)
        raw_tree = simple_processing_accessiblity_tree(tree.raw, config)
        if raw_tree is None:
            raise NodeFilteringResultsInEmptyGraph("pruning raw tree")
        raw_tree = sync_ids_between_trees(source=simple_tree, target=raw_tree)
        # manually add IDs to images
        raw_tree = generate_sequential_ids(raw_tree, only_for=set(["image", "img"]))

        _processed_tree = complex_processing_accessiblity_tree(tree.raw, config)
        processed_tree = simple_processing_accessiblity_tree(_processed_tree, config)
        if processed_tree is None:
            raise NodeFilteringResultsInEmptyGraph("pruning processed tree")
        processed_tree = sync_ids_between_trees(source=simple_tree, target=processed_tree)
        # manually sync image IDs between trees
        processed_tree = sync_image_ids_between_trees(source=raw_tree, target=processed_tree)
        # ASSUMPTION: only dialog actions are relevant if present
        processed_tree = prune_non_dialogs_if_present(processed_tree)
        # TODO: enable that if really needed
        # processed_tree = prune_text_nodes(processed_tree)

        # Be aware that this call updates the IDs of the snapshot raw tree
        tree.raw = sync_ids_between_trees(source=simple_tree, target=tree.raw)

        return ProcessedA11yTree(processed_tree=processed_tree, raw_tree=raw_tree, simple_tree=simple_tree)

    def tree(self, type: str = "processed") -> A11yNode:
        match type:
            case "processed":
                return self.processed_tree
            case "simple":
                return self.simple_tree
            case "raw":
                return self.raw_tree
            case _:
                raise InvalidA11yTreeType(type)

    def interaction_nodes(self, type: str = "processed", parent_path: str | None = None) -> list[A11yNode]:
        match type:
            case "processed":
                return list_interactive_nodes(self.processed_tree, parent_path=parent_path, only_with_id=True)
            case "simple":
                return list_interactive_nodes(self.simple_tree, parent_path=parent_path, only_with_id=True)
            case "raw":
                return list_interactive_nodes(self.raw_tree, parent_path=parent_path, only_with_id=True)
            case _:
                raise InvalidA11yTreeType(type)

    def visualize(self, type: str = "processed") -> str:
        match type:
            case "processed":
                return visualize_a11y_tree(self.processed_tree)
            case "simple":
                return visualize_a11y_tree(self.simple_tree)
            case "raw":
                return visualize_a11y_tree(self.raw_tree)
            case _:
                raise InvalidA11yTreeType(type)

    def find_node_path_by_id(self, id: str, type: str = "processed") -> list[A11yNode] | None:
        match type:
            case "processed":
                return find_node_path_by_id(node=self.processed_tree, notte_id=id)
            case "simple":
                return find_node_path_by_id(node=self.simple_tree, notte_id=id)
            case "raw":
                return find_node_path_by_id(node=self.raw_tree, notte_id=id)
            case _:
                raise InvalidA11yTreeType(type)

    def find_all_paths_by_role_and_name(self, role: str, name: str, type: str = "processed") -> list[list[A11yNode]]:
        match type:
            case "processed":
                return find_all_paths_by_role_and_name(node=self.processed_tree, role=role, name=name)
            case "simple":
                return find_all_paths_by_role_and_name(node=self.simple_tree, role=role, name=name)
            case "raw":
                return find_all_paths_by_role_and_name(node=self.raw_tree, role=role, name=name)
            case _:
                raise InvalidA11yTreeType(type)

    def find_node_by_id(self, id: str, type: str = "processed") -> A11yNode | None:
        path = self.find_node_path_by_id(id=id, type=type)
        if path is None:
            return None
        return path[0]

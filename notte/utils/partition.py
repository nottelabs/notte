from notte.browser.node_type import NotteNode


def find_node_by_path(root: NotteNode, path: list[int]) -> NotteNode:
    way = path[0] if len(path) > 0 else None
    if way is None:
        return root
    return find_node_by_path(root.children[way], path[1:])


def partial_tree_by_path(root: NotteNode, path: list[int]) -> NotteNode:
    way = path[0] if len(path) > 0 else None
    if way is None:
        return root
    subtree = partial_tree_by_path(root.children[way], path[1:])
    return NotteNode(id=root.id, role=root.role, text=root.text, children=[subtree])


def merge_trees(trees: list[NotteNode]) -> NotteNode | None:
    if not trees:  # check if the list is empty
        return None

    # check if all trees have the same root hash
    root_hash = trees[0].__hash__()
    if not all(tree.__hash__() == root_hash for tree in trees):
        raise ValueError("Cannot merge trees with different root hashes")

    # create a new merged tree with the same root
    merged_tree = NotteNode(id=trees[0].id, role=trees[0].role, text=trees[0].text)

    # create a dictionary to track children by their text across all trees
    children_map: dict[int, list[NotteNode]] = {}

    # collect children from all trees
    for tree in trees:
        for child in tree.children:
            if child.__hash__() not in children_map:
                children_map[child.__hash__()] = []
            children_map[child.__hash__()].append(child)

    # process each unique child hash
    for _, child_nodes in children_map.items():
        # if multiple children with the same hash exist, recursively merge them
        if len(child_nodes) > 1:
            merged_child = merge_trees(child_nodes)
            if merged_child is not None:
                merged_tree.children.append(merged_child)
        else:
            # if only one child exists, add it directly
            merged_tree.children.append(child_nodes[0])

    return merged_tree


def split(node: NotteNode, gamma: int) -> list[NotteNode]:
    # The objective is to get a list of nodes fitting gamma.
    # > this function does a sort of breadth search to split each
    # node into their subnodes; until all of the nodes in the
    # resulting list fit the gamma thresholding condition.
    if node._chars == -1:
        raise ValueError("Node _chars has not been computed yet")
    if node._chars <= gamma:
        return [node]
    if len(node.children) == 0:
        raise ValueError("Move to notte.sdk to handle very long context webpages.")
    ls: list[NotteNode] = []
    for child in node.children:
        if child._chars <= gamma:
            ls.append(child)
        else:
            ls.extend(split(child, gamma))
    return ls


def partition(arr: list[int], gamma: int) -> list[list[int]]:
    n = len(arr)

    # dp to track minimum partitions
    # dp[i] will store the minimum number of partitions for subarray up to index i
    dp = [float("inf")] * n

    # stores the indices where partitions start
    partition_starts: list[list[list[int]]] = [[] for _ in range(n)]

    # base case: first element
    if arr[0] <= gamma:
        dp[0] = 1
        partition_starts[0] = [[0]]

    # fill dp table
    for i in range(1, n):
        # try all possible last partition starting points
        curr_sum = 0
        for j in range(i, -1, -1):
            curr_sum += arr[j]

            # if current sum exceeds gamma, break
            if curr_sum > gamma:
                break

            # calculate partitions up to j-1
            prev_partitions = float("inf")
            if j > 0:
                prev_partitions = dp[j - 1]
            else:
                prev_partitions = 0

            # update if we find a better partitioning
            if prev_partitions + 1 < dp[i]:
                dp[i] = prev_partitions + 1

                # copy previous partitions and add current partition
                if j > 0:
                    partition_starts[i] = [p + [j] for p in partition_starts[j - 1]]
                else:
                    partition_starts[i] = [[j]]

    # find the best partitioning
    if dp[n - 1] == float("inf"):
        return []

    # reconstruct the actual partitions
    best_partitions = partition_starts[n - 1][0]
    best_partitions.append(n)

    # convert partition starts to actual partitions
    result_partitions: list[list[int]] = []
    for start, end in zip(best_partitions[:-1], best_partitions[1:]):
        result_partitions.append(list(range(start, end)))

    return result_partitions

# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
# Inverts a binary tree by swapping left and right subtrees recursively.
class Solution:
    def invertTree(self, root: Optional[TreeNode]) -> Optional[TreeNode]:
        # Base case: if the node is None, return None
        if root is None:
            return None

        # Recursively invert the left and right subtrees
        inverted_left = self.invertTree(root.left)
        inverted_right = self.invertTree(root.right)

        # Swap the left and right children of the current node
        root.left = inverted_right
        root.right = inverted_left

        # Return the root node with its children swapped
        return root

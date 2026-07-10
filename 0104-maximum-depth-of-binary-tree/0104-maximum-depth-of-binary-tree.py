# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
class Solution:
    def maxDepth(self, root: Optional[TreeNode]) -> int:
        # Base case: an empty tree has depth 0
        if not root:
            return 0
        # Ask each subtree the same question and trust the answer
        left = self.maxDepth(root.left)
        right = self.maxDepth(root.right)

        # Combine: this node adds 1 on top of its deeper subtree
        return 1 + max(left, right)
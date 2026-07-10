# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
class Solution:
    def diameterOfBinaryTree(self, root: Optional[TreeNode]) -> int:
        self.res = 0

        # Returns height
        def dfs(cur):
            if not cur:
                return 0

            # height of left subtree
            left = dfs(cur.left)
            # height of right subtree
            right = dfs(cur.right)
            # update the shared result with this node's candidate:
            self.res = max(self.res, left + right)
            return 1 + max(left, right)
        dfs(root)
        return self.res
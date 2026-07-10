# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
class Solution:
    def isSameTree(self, p: Optional[TreeNode], q: Optional[TreeNode]) -> bool:
        # Two trees are identical if they have the same structure and node values.
        
        # Base case: both nodes are None
        if not p and not q:
            return True

        # If only one node is None or values don't match, trees are different
        if not p or not q or p.val != q.val:
            return False
        
        # Recursively check if left subtrees and right subtrees are identical
        # Both subtrees must be identical for the trees to be the same
        left_same = self.isSameTree(p.left, q.left)
        right_same = self.isSameTree(p.right, q.right)

        return left_same and right_same
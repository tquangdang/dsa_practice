# Definition for a binary tree node.
# class TreeNode:
#     def __init__(self, val=0, left=None, right=None):
#         self.val = val
#         self.left = left
#         self.right = right
class Solution:
    def isBalanced(self, root: Optional[TreeNode]) -> bool:
        def calculate_height(node: Optional[TreeNode]) -> int:
            """
            Calculates the height of a subtree while checking if it's balanced.
            Args:
                node: Current node being processed
            Returns:
                The height of the subtree if balanced, -1 if unbalanced
            """
            # Base case: empty node has height 0
            if not node:
                return 0
            # Recursively calculate heights of left and right subtrees
            left = calculate_height(node.left)
            right = calculate_height(node.right)
        
            # Check if any subtree is unbalanced or if current node violates balance condition
            if (left == -1 or 
                right == -1 or 
                abs(left - right) > 1):
                return -1  # Return -1 to indicate unbalanced tree

            # Return height of current subtree (1 + maximum height of children)
            return 1 + max(left, right)
        
        # Tree is balanced if height calculation doesn't return -1
        return calculate_height(root) >= 0
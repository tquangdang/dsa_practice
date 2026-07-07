"""
# Definition for a Node.
class Node:
    def __init__(self, x: int, next: 'Node' = None, random: 'Node' = None):
        self.val = int(x)
        self.next = next
        self.random = random
"""

class Solution:
    def copyRandomList(self, head: 'Optional[Node]') -> 'Optional[Node]':
        # Create a hash map oldToCopy, mapping each original node to its copied node.
        # Include null -> null for convenience.
        oldToCopy = {None: None}
        cur = head
        # First pass: iterate through the original list
            # Create a copy of each node.
            # Store the mapping in oldToCopy.
        while cur:
            copy = Node(cur.val)
            oldToCopy[cur] = copy
            cur = cur.next
        
        cur = head
        # Second pass: iterate again
            # Set copy.next using oldToCopy[original.next].
            # Set copy.random using oldToCopy[original.random].
        while cur:
            copy = oldToCopy[cur]
            copy.next = oldToCopy[cur.next]
            copy.random = oldToCopy[cur.random]
            cur = cur.next
        
        # Return the copied version of the head using oldToCopy[head].
        return oldToCopy[head]
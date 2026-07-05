# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def removeNthFromEnd(self, head: Optional[ListNode], n: int) -> Optional[ListNode]:
        # Count the number of element in the list
        size = 0
        cur = head
        while cur:
            size += 1
            cur = cur.next
        # Delete the element, using a dummy node
        dummy = ListNode(0, head)
        # Initialize previous, so we dont lose dummy 
        previous = dummy
        cur = head
        for i in range(size - n):
            previous = previous.next
            cur = cur.next
        # At this moment, previous is the node on the left
        # of the node we need to delete
        temp = cur.next
        previous.next = cur.next
        cur.next = None

        # use dummy to return, in case the head is the node need to remove
        return dummy.next
            
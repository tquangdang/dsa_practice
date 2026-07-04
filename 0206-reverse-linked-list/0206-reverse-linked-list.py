# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:
        prev, cur = None, head
        while cur:
            # Get the next node from current, and save it to a temp var
            temp = cur.next
            # Reverse the list
            cur.next = prev
            prev = cur
            cur = temp
        return prev
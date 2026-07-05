# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def reorderList(self, head: Optional[ListNode]) -> None:
        """
        Find the middle with fast/slow pointers 
        reverse the second half in place, then weave the two halves together by alternating nodes.
        """
        # Find the middle
        fast = slow = head
        while fast.next and fast.next.next:
            slow = slow.next
            fast = fast.next.next
        # Cut off the second half. cur is the head of the second half
        cur = slow.next
        slow.next = None
        # Then reverse
        previous = None
        while cur:
            temp = cur.next
            cur.next = previous
            previous = cur
            cur = temp
        # After this loop, previous points to the head of the reversed second half.
        # We merge the two halves hlternately
        cur = head
        while previous:
            temp1, temp2 = cur.next, previous.next
            cur.next = previous
            previous.next = temp1
            # cur step to the first half's next node. previous step to the second half's next node
            cur = temp1
            previous = temp2
        return head



'''
1 -> 2
4 -> 3

'''


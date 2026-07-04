# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def mergeTwoLists(self, list1: Optional[ListNode], list2: Optional[ListNode]) -> Optional[ListNode]:
        # Use a dummy head to create a new list
        # result will remain as the beginning of the list (to return later)
        dummy = ListNode()
        result = dummy

        # Use list1 and list2 as head
        while list1 and list2:
            if list1.val <= list2.val:
                dummy.next = ListNode(list1.val)
                list1 = list1.next
            else:
                dummy.next = ListNode(list2.val)
                list2 = list2.next
            dummy = dummy.next
        dummy.next = list1 or list2

        return result.next
       
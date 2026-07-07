# Definition for singly-linked list.
# class ListNode:
#     def __init__(self, val=0, next=None):
#         self.val = val
#         self.next = next
class Solution:
    def addTwoNumbers(self, l1: Optional[ListNode], l2: Optional[ListNode]) -> Optional[ListNode]:
        # carry holds the "1" carried over from the previous digit column (starts at 0)
        carry = 0
        # dummy is a placeholder node so we never handle "empty head" as a special case;
        # result is the pointer that walks forward and builds the answer list
        result = dummy = ListNode(0)
        num1, num2 = l1, l2
        # Keep looping while EITHER list still has digits OR a carry is left over.
        # The "or carry" handles cases like 99 + 1: both lists run out
        # but we still owe one final node for the leftover carry.
        while num1 or num2 or carry:
            # If a list has run out, treat its digit as 0
            # (like adding 099 + 001 on paper)
            if num1:
                num1_val = num1.val
            else:
                num1_val = 0
            if num2:
                num2_val = num2.val
            else:
                num2_val = 0

            # Add the two digits in this column plus the carry from the last column
            total = num1_val + num2_val + carry
            # total is at most 9 + 9 + 1 = 19, so:
            # carry = total // 10  -> 1 if total >= 10, else 0
            carry = total // 10
            # total % 10 -> the digit that stays in this column
            # (e.g. total = 14 -> write 4, carry 1; total = 7 -> write 7, carry 0)
            result.next = ListNode(total % 10)

            # Advance each list only if it still has nodes left
            if num1:
                num1 = num1.next
            if num2:
                num2 = num2.next

            # Move the builder pointer to the node we just created
            result = result.next
        # dummy.val is the fake 0 we started with; the real answer begins at dummy.next
        return dummy.next
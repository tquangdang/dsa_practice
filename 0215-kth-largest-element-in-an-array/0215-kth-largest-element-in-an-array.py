class Solution:
    def findKthLargest(self, nums: List[int], k: int) -> int:
        heap = [-num for num in nums]
        heapify(heap)
        for i in range(k - 1):
            heappop(heap)
        return -heap[0]
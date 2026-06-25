class Solution:
    def lastStoneWeight(self, stones: List[int]) -> int:
        # Sorting every time would be wasteful. A heap would be handy
        
        # Negatives make Python's min heap behave like a max heap
        heap = [-stone for stone in stones]
        heapify(heap)
        while len(heap) > 1:
            x = -heappop(heap)  # heaviest
            y = -heappop(heap)  # second heaviest

            if x != y:
                heappush(heap, -(x - y))
        if heap:
            return -heap[0]
        return 0



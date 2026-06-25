import heapq
class Solution:
    def kClosest(self, points: List[List[int]], k: int) -> List[List[int]]:
        result = []
        # Create a min heap
        minHeap = []
        # Loop through the array
        for point in points:
            # Calculate the distance
            distance = (point[0] ** 2) + (point[1] ** 2)
            minHeap.append([distance, point[0], point[1]])
        # Heapify
        heapify(minHeap)
        # Loop and collect the result
        for i in range(k):
            minDistance = heappop(minHeap)
            result.append([minDistance[1], minDistance[2]])   
            
        return result 
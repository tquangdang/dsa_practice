class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        numDict = defaultdict(int)
        heap = []
        result = []
        for num in nums:
            if num not in numDict:
                numDict[num] = 1
            else:
                numDict[num] += 1

        for key, value in numDict.items():
            heap.append((value * -1, key))
        heapify(heap)

        for _ in range(k):
            result.append(heappop(heap)[1])
        return result
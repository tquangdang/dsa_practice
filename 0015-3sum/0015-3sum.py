'''
nums = [-1,0,1,2,-1,-4]
       [-4, -1, -1, -1, 0, 1, 2, 2]
             i   
                        j  
                              k
        
res = [-1, -1, 2] [-1, 0, 1]  

                 
'''

class Solution:
    def threeSum(self, nums: List[int]) -> List[List[int]]:
        res = []
        # sort the array
        nums.sort()
        
        for i in range(len(nums)):
            # skip over duplicate 
            if i > 0 and nums[i] == nums[i-1]:
                continue
            # 2 pointers
            j, k = i + 1, len(nums)-1
            while j < k:
                if nums[i] + nums[j] + nums[k] > 0:
                    k -= 1
                elif nums[i] + nums[j] + nums[k] < 0:
                    j += 1
                else:
                    res.append([nums[i],nums[j], nums[k]])
                    j += 1
                    k -= 1
                    # move j to unique number
                    while nums[j-1] == nums[j] and j < k:
                        j += 1
        
        return res
            
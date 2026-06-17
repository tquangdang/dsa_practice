class Solution:
    def groupAnagrams(self, strs: List[str]) -> List[List[str]]:
        wordDict = defaultdict(list)
        
        for word in strs:
            key = "".join(sorted(word))
            wordDict[key].append(word)
        return list(wordDict.values())
           
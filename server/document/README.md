# Model Generation
1- Prepare the entities:
* Enumerate all values of each entity. Each entity must be saved in a separate file.

*	The proposed APIs are:
	*	POST /entity/{entityName}: create or add an entity
	*	PUT /entity/{entityName}: create or overwrite an entity
	*	DELETE /entity/{entityName}: delete an entity

	Example:
	**entity 'ville'**
	>	Toulouse
Rome
Paris
Bastille
Rouen
Valence
Orléans
Dijon

	**entity 'number'**
	> un
deux
trois
quatre
cinq
six
sept
huit
neuf
dix

2- Prepare the intents:
* Create a user-specific intent. Each intent should be created in a separate file. Two intent file format are supported by the API. The first is a simple raw text file in which each line is a command and the entity must be marked by an _Hash_ key  '#'.

*	The proposed APIs are:
	*	PUT /intent/{intentName}: create or overwrite an intent
	*	DELETE /intent/{intentName}: delete an intent

	Example:
	**intent 'ville'**
	```	
	quel est le niveau de pollution à #location
	donne moi le niveau de pollution à #location
	comment est la pollution à #location
	```

	The second file format is a markdown file.

	Example
	**intent 'ville'**
	```
	 - quel est le niveau de pollution à [bastia](location)
	 - donne moi le niveau de pollution à [Tokyo](location)
	 - comment est la pollution à [Hikone](location)
	```

